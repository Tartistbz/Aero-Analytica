"""Bounded bridge between the Streamlit workspace and the RepoPilot CLI.

RepoPilot remains the owner of agent execution.  This module only discovers
checked-in tasks, starts the local CLI with argument arrays, and reads its
immutable run artifacts for display.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from src.ai.providers import (
    ANTHROPIC_COMPATIBLE,
    OPENAI_COMPATIBLE,
    ProviderConfig,
)


DEFAULT_TIMEOUT_SECONDS = 15 * 60
MAX_OUTPUT_CHARACTERS = 120_000
MAX_ARTIFACT_TEXT_CHARACTERS = 120_000
MAX_TRACE_EVENTS = 100


class RepoPilotServiceError(RuntimeError):
    """Raised when the local RepoPilot runtime cannot be started safely."""


@dataclass(frozen=True)
class TaskOption:
    path: Path
    relative_path: str
    task_id: str
    prompt: str

    @property
    def domain(self) -> str:
        parts = Path(self.relative_path).parts
        return parts[0].upper() if parts else "TASK"

    @property
    def label(self) -> str:
        return f"[{self.domain}] {self.task_id}"


@dataclass(frozen=True)
class SuiteOption:
    path: Path
    relative_path: str
    task_count: int

    @property
    def label(self) -> str:
        return f"{self.path.stem} ({self.task_count} 项)"


@dataclass(frozen=True)
class CliInvocation:
    command: tuple[str, ...]
    returncode: Optional[int]
    duration_ms: int
    payload: Optional[dict[str, Any]]
    stdout: str
    stderr: str
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and self.payload is not None and self.error is None


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def runtime_status(*, root: Optional[Path] = None) -> dict[str, bool]:
    """Return only local dependency availability; no commands are executed."""

    root = Path(root or project_root()).resolve()
    return {
        "npm": _find_executable("npm") is not None,
        "node": _find_executable("node") is not None,
        "cli": (root / "repopilot" / "src" / "cli.ts").is_file(),
        "dependencies": (root / "node_modules" / "tsx").exists(),
    }


def discover_tasks(*, root: Optional[Path] = None) -> list[TaskOption]:
    root = Path(root or project_root()).resolve()
    tasks_root = root / "evals" / "tasks"
    if not tasks_root.is_dir():
        return []

    tasks: list[TaskOption] = []
    for path in sorted(tasks_root.rglob("*.yml")):
        task_id = _yaml_scalar(path, "id") or path.stem
        prompt = _yaml_scalar(path, "prompt") or ""
        tasks.append(
            TaskOption(
                path=path.resolve(),
                relative_path=path.relative_to(tasks_root).as_posix(),
                task_id=task_id,
                prompt=prompt,
            )
        )
    return tasks


def discover_suites(*, root: Optional[Path] = None) -> list[SuiteOption]:
    root = Path(root or project_root()).resolve()
    suites_root = root / "evals" / "suites"
    if not suites_root.is_dir():
        return []

    suites: list[SuiteOption] = []
    for path in sorted(suites_root.glob("*.yml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        task_count = len(re.findall(r"^\s*-\s+", text, flags=re.MULTILINE))
        suites.append(
            SuiteOption(
                path=path.resolve(),
                relative_path=path.relative_to(suites_root).as_posix(),
                task_count=task_count,
            )
        )
    return suites


def pi_environment(provider: ProviderConfig) -> dict[str, str]:
    """Translate the active Aero-Analytica Provider for one Pi process only."""

    provider.validate()
    if provider.protocol == OPENAI_COMPATIBLE:
        api = "openai-completions"
    elif provider.protocol == ANTHROPIC_COMPATIBLE:
        api = "anthropic-messages"
    else:
        raise RepoPilotServiceError(f"当前 Provider 协议不能用于 Pi：{provider.protocol}")
    if not provider.api_key:
        raise RepoPilotServiceError("当前 Provider 没有 API Key，无法启动 Pi 运行")

    return {
        "REPOPILOT_PI_PROVIDER": f"aero-{provider.id}",
        "REPOPILOT_PI_MODEL": provider.model,
        "REPOPILOT_PI_BASE_URL": provider.base_url,
        "REPOPILOT_PI_API": api,
        "REPOPILOT_PI_API_KEY": provider.api_key,
        "REPOPILOT_PI_HEADERS": json.dumps(provider.custom_headers),
    }


def run_evaluation(
    *,
    suite: Optional[Path] = None,
    task: Optional[Path] = None,
    runtime: str = "fake",
    strategy: str = "focused",
    pi_env: Optional[Mapping[str, str]] = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    root: Optional[Path] = None,
) -> CliInvocation:
    """Run one checked-in suite or task through RepoPilot's ``eval`` command."""

    root = Path(root or project_root()).resolve()
    if (suite is None) == (task is None):
        raise RepoPilotServiceError("请选择一个任务集或单个任务")
    if runtime not in {"fake", "pi"}:
        raise RepoPilotServiceError("运行模式只能是 fake 或 pi")
    if strategy not in {"map-only", "focused", "focused+history"}:
        raise RepoPilotServiceError("未知的上下文策略")

    report_path = _new_report_path(root)
    if suite is not None:
        suite_path = _checked_path(suite, root / "evals" / "suites", "任务集")
        return _invoke_eval(
            root=root,
            suite_path=suite_path,
            runtime=runtime,
            strategy=strategy,
            report_path=report_path,
            pi_env=pi_env,
            timeout_seconds=timeout_seconds,
        )

    task_path = _checked_path(task, root / "evals" / "tasks", "任务")
    with tempfile.TemporaryDirectory(prefix="repopilot-ui-") as temp_dir:
        single_suite = Path(temp_dir) / "single-task.yml"
        single_suite.write_text(
            f"tasks:\n  - {json.dumps(task_path.as_posix())}\n",
            encoding="utf-8",
        )
        return _invoke_eval(
            root=root,
            suite_path=single_suite,
            runtime=runtime,
            strategy=strategy,
            report_path=report_path,
            pi_env=pi_env,
            timeout_seconds=timeout_seconds,
        )


def replay_run(
    run_dir: Path,
    *,
    timeout_seconds: int = 60,
    root: Optional[Path] = None,
) -> CliInvocation:
    """Ask the CLI to replay an existing trace without calling a model."""

    root = Path(root or project_root()).resolve()
    run_dir = Path(run_dir).resolve()
    if not (run_dir / "events.jsonl").is_file():
        raise RepoPilotServiceError("运行产物中缺少 events.jsonl，无法回放")
    return _run_cli(
        ["replay", "--run", str(run_dir)],
        root=root,
        timeout_seconds=timeout_seconds,
    )


def load_run_artifact(run_dir: Path) -> dict[str, Any]:
    """Load bounded, display-safe data from one completed run directory."""

    run_dir = Path(run_dir).resolve()
    metadata = _load_json(run_dir / "metadata.json")
    context = _load_json(run_dir / "context.json")
    trace = _read_trace(run_dir / "events.jsonl")
    verification = metadata.get("verification")
    if not isinstance(verification, dict):
        verification = {"ok": False, "checks": []}
    checks = verification.get("checks")
    if not isinstance(checks, list):
        checks = []

    return {
        "run_dir": str(run_dir),
        "run_id": str(metadata.get("runId") or run_dir.name),
        "task_id": str(metadata.get("taskId") or "unknown"),
        "status": str(metadata.get("status") or trace["status"] or "unknown"),
        "failure_category": verification.get("failureCategory"),
        "verification": {
            "ok": bool(verification.get("ok")),
            "checks": [
                {
                    "name": str(check.get("name", "unknown")),
                    "ok": bool(check.get("ok")),
                    "duration_ms": int(check.get("durationMs", 0) or 0),
                    "output": _display_text(str(check.get("output", ""))),
                }
                for check in checks
                if isinstance(check, dict)
            ],
        },
        "context": {
            "strategy": context.get("strategy"),
            "estimated_tokens": context.get("estimatedTokens", 0),
            "budget_tokens": context.get("budgetTokens", 0),
            "selected_files": context.get("selectedFiles", []),
            "dropped_files": context.get("droppedFiles", []),
        },
        "trace": trace,
        "diff": _read_bounded_text(run_dir / "final.diff"),
        "report_path": str(run_dir / "report.html") if (run_dir / "report.html").is_file() else None,
    }


def load_eval_artifacts(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        return []
    artifacts: list[dict[str, Any]] = []
    for row in tasks:
        if not isinstance(row, dict) or not row.get("runDir"):
            continue
        try:
            artifact = load_run_artifact(Path(str(row["runDir"])))
        except OSError:
            artifact = {
                "run_dir": str(row["runDir"]),
                "run_id": str(row.get("runId", "unknown")),
                "task_id": str(row.get("id", "unknown")),
                "status": str(row.get("status", "unknown")),
                "failure_category": row.get("failureCategory"),
                "unavailable": True,
            }
        artifact["metrics"] = {
            "tool_calls": int(row.get("toolCalls", 0) or 0),
            "duration_ms": int(row.get("durationMs", 0) or 0),
            "context_tokens": int(row.get("contextTokens", 0) or 0),
            "selected_files": int(row.get("selectedFiles", 0) or 0),
            "recovery_count": int(row.get("recoveryCount", 0) or 0),
            "test_passed": bool(row.get("testPassed")),
        }
        artifacts.append(artifact)
    return artifacts


def _invoke_eval(
    *,
    root: Path,
    suite_path: Path,
    runtime: str,
    strategy: str,
    report_path: Path,
    pi_env: Optional[Mapping[str, str]],
    timeout_seconds: int,
) -> CliInvocation:
    return _run_cli(
        [
            "eval",
            "--suite",
            str(suite_path),
            "--runtime",
            runtime,
            "--strategy",
            strategy,
            "--report",
            str(report_path),
        ],
        root=root,
        timeout_seconds=timeout_seconds,
        extra_env=pi_env,
    )


def _run_cli(
    arguments: Sequence[str],
    *,
    root: Path,
    timeout_seconds: int,
    extra_env: Optional[Mapping[str, str]] = None,
) -> CliInvocation:
    npm = _find_executable("npm")
    if npm is None:
        raise RepoPilotServiceError("未找到 npm。请安装 Node.js 并重启 Streamlit。")
    if not (root / "repopilot" / "src" / "cli.ts").is_file():
        raise RepoPilotServiceError("未找到 RepoPilot CLI 源码。")
    if not (root / "node_modules" / "tsx").exists():
        raise RepoPilotServiceError("RepoPilot 依赖尚未安装。请先在项目根目录运行 npm install。")

    command = (npm, "run", "repopilot", "--", *arguments)
    environment = os.environ.copy()
    if extra_env:
        environment.update({key: value for key, value in extra_env.items() if value})
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - started) * 1000)
        return CliInvocation(
            command=command,
            returncode=None,
            duration_ms=duration_ms,
            payload=None,
            stdout="",
            stderr="",
            error=f"RepoPilot 运行超过 {timeout_seconds} 秒，已终止。",
        )
    except OSError as exc:
        raise RepoPilotServiceError(f"无法启动 RepoPilot：{exc}") from exc

    stdout = _display_text(completed.stdout)
    stderr = _display_text(completed.stderr)
    payload = _parse_last_json_object(completed.stdout)
    error = None
    if payload is None:
        error = "RepoPilot 没有返回可读取的 JSON 结果。"
    elif completed.returncode != 0:
        error = f"RepoPilot 以退出码 {completed.returncode} 结束。"
    return CliInvocation(
        command=command,
        returncode=completed.returncode,
        duration_ms=int((time.monotonic() - started) * 1000),
        payload=payload,
        stdout=stdout,
        stderr=stderr,
        error=error,
    )


def _find_executable(name: str) -> Optional[str]:
    candidates = [name]
    if os.name == "nt":
        candidates.insert(0, f"{name}.cmd")
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _checked_path(path: Path, parent: Path, label: str) -> Path:
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(parent.resolve())
    except ValueError as exc:
        raise RepoPilotServiceError(f"{label}必须位于 {parent} 内") from exc
    if not resolved.is_file():
        raise RepoPilotServiceError(f"{label}文件不存在：{resolved}")
    return resolved


def _new_report_path(root: Path) -> Path:
    reports = root / ".repopilot" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    return reports / f"ui-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.html"


def _yaml_scalar(path: Path, key: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if not match:
        return ""
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        value = value[1:-1]
    return value


def _parse_last_json_object(text: str) -> Optional[dict[str, Any]]:
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for match in re.finditer(r"\{", text):
        try:
            candidate, end_index = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            trailing = text[match.start() + end_index :]
            if not trailing.strip():
                return candidate
            candidates.append((end_index, candidate))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_trace(path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    events: list[dict[str, str]] = []
    final_status: Optional[str] = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("type", "unknown"))
                counts[event_type] += 1
                if event_type == "run_finished" and isinstance(event.get("payload"), dict):
                    final_status = str(event["payload"].get("status") or "") or None
                events.append(
                    {
                        "timestamp": str(event.get("timestamp", "")),
                        "type": event_type,
                    }
                )
    except OSError:
        pass
    return {
        "event_count": sum(counts.values()),
        "tool_calls": counts["tool_call"],
        "verification_events": counts["verification"],
        "recovery_count": counts["tool_retry"] + counts["run_resumed"],
        "status": final_status,
        "event_types": dict(sorted(counts.items())),
        "timeline": events[-MAX_TRACE_EVENTS:],
    }


def _read_bounded_text(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(MAX_ARTIFACT_TEXT_CHARACTERS + 1)
    except OSError:
        return ""
    return _display_text(text)


def _display_text(value: str) -> str:
    value = re.sub(
        r"(?i)(api[_-]?key|authorization|token|secret|password)(\s*[=:]\s*)([^\s,;\"']+)",
        r"\1\2[REDACTED]",
        value,
    )
    value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._-]+", "Bearer [REDACTED]", value)
    if len(value) > MAX_OUTPUT_CHARACTERS:
        return f"{value[:MAX_OUTPUT_CHARACTERS]}\n\n[输出已截断]"
    return value
