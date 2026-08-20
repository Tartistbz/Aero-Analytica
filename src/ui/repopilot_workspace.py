"""Code-repair workspace backed by the internal RepoPilot execution harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

import streamlit as st

from src.ai.providers import ProviderConfig
from src.repopilot.service import (
    CliInvocation,
    RepoPilotServiceError,
    RepositoryInspection,
    create_repair_task,
    discover_suites,
    discover_tasks,
    inspect_repository,
    load_eval_artifacts,
    pi_environment,
    replay_run,
    run_evaluation,
    run_repository_task,
    runtime_status,
    to_evaluation_payload,
)


RUNTIME_LABELS = {"fake": "确定性 Fake", "pi": "Pi Agent"}
STRATEGY_LABELS = {
    "map-only": "仅仓库地图",
    "focused": "聚焦文件",
    "focused+history": "聚焦文件 + 历史压缩",
}
PLATFORM_OPTIONS = (
    "PX4",
    "ArduPilot",
    "ROS / ROS 2",
    "Aero-Analytica / 其他 Python 项目",
    "其他 Git 项目",
)
PLATFORM_SCOPES = {
    "PX4": "src/**, msg/**, platforms/**, test/**, tests/**",
    "ArduPilot": "libraries/**, ArduCopter/**, ArduPlane/**, Tools/**, tests/**",
    "ROS / ROS 2": "src/**, include/**, launch/**, config/**, test/**, tests/**",
    "Aero-Analytica / 其他 Python 项目": "app.py, src/**, tests/**",
    "其他 Git 项目": "src/**, lib/**, include/**, test/**, tests/**",
}
VALIDATION_HINTS = {
    "PX4": "填写项目中实际可运行的目标测试或构建命令，例如 make <target> 或单个测试命令。",
    "ArduPilot": "填写项目中实际可运行的测试命令，例如 waf 或 autotest 的具体目标。",
    "ROS / ROS 2": "填写项目中实际可运行的验证命令，例如 colcon test --packages-select <包名>。",
    "Aero-Analytica / 其他 Python 项目": "例如 C:\\ProgramData\\Miniconda3\\envs\\uav-log-env\\python.exe -m unittest discover -s tests -v。",
    "其他 Git 项目": "填写项目当前可运行的测试、类型检查或构建命令，一行一个。",
}
REPAIR_REQUEST_KEY = "repopilot_repair_request"
REPAIR_RESULT_KEY = "repopilot_repair_result"
FIXTURE_RESULT_KEY = "repopilot_fixture_evaluation"
REPOSITORY_RESULT_KEY = "repopilot_repository_evaluation"


def render_repopilot_workspace(active_provider: Optional[ProviderConfig]) -> None:
    """Render the user-facing repair flow and collapsed harness controls."""

    status = runtime_status()
    if not all(status.values()):
        missing = []
        if not status["node"]:
            missing.append("Node.js")
        if not status["npm"]:
            missing.append("npm")
        if not status["dependencies"]:
            missing.append("node_modules")
        if not status["cli"]:
            missing.append("代码修复执行组件")
        st.error(f"代码问题修复不可用：缺少 {', '.join(missing)}")
        return

    st.subheader("代码问题修复")
    st.caption("定位 PX4、ArduPilot、ROS 和机器人项目中的报错或异常；AI 只会在隔离副本中修改代码。")
    _render_repair_workspace(active_provider)

    with st.expander("开发者工具", expanded=False):
        st.caption("用于维护任务集、比较 Agent 策略和查看底层执行证据，不是日常代码修复的必需步骤。")
        bundled_tab, yaml_tab = st.tabs(["内置任务评测", "导入任务 YAML"])
        with bundled_tab:
            _render_bundled_evaluation(active_provider)
        with yaml_tab:
            _render_repository_evaluation(active_provider)


def _render_repair_workspace(active_provider: Optional[ProviderConfig]) -> None:
    platform = st.selectbox("目标平台", PLATFORM_OPTIONS, key="repopilot_repair_platform")
    allowed_paths_key = f"repopilot_repair_allowed_paths_{PLATFORM_OPTIONS.index(platform)}"
    with st.form("repopilot_repair_form", border=False):
        repository_path = st.text_input(
            "代码仓库路径",
            placeholder=r"D:\work\PX4-Autopilot",
            help="选择包含 .git 的本地仓库。原仓库不会被直接修改。",
            key="repopilot_repair_repository_path",
        )
        problem = st.text_area(
            "遇到的问题",
            placeholder="粘贴完整报错、测试输出，或描述复现步骤和预期行为。",
            height=140,
            key="repopilot_repair_problem",
        )
        test_commands_text = st.text_area(
            "验证命令",
            placeholder="一行一个命令，例如：\npython -m unittest discover -s tests -v",
            help="修复结束后会在隔离副本执行这些命令。不同项目命令不同，需要由仓库使用者确认。",
            height=90,
            key="repopilot_repair_test_commands",
        )
        allowed_paths_text = st.text_input(
            "允许修改的范围",
            value=PLATFORM_SCOPES[platform],
            help="逗号分隔的仓库内相对路径或 glob。范围以外的改动会被验证器拒绝。",
            key=allowed_paths_key,
        )
        preview_clicked = st.form_submit_button("检查并预览修复", type="primary", width="stretch")

    signature = _repair_signature(platform, repository_path, problem, test_commands_text, allowed_paths_text)
    if preview_clicked:
        _prepare_repair_request(
            platform=platform,
            repository_path=repository_path,
            problem=problem,
            test_commands_text=test_commands_text,
            allowed_paths_text=allowed_paths_text,
            signature=signature,
        )

    request = st.session_state.get(REPAIR_REQUEST_KEY)
    if request and request.get("signature") != signature:
        st.info("输入已更新。请再次点击“检查并预览修复”，再启动新的修复任务。")
        request = None
    if request:
        _render_repair_preview(request, active_provider)

    invocation = st.session_state.get(REPAIR_RESULT_KEY)
    if isinstance(invocation, CliInvocation):
        _render_repair_result(invocation)


def _prepare_repair_request(
    *,
    platform: str,
    repository_path: str,
    problem: str,
    test_commands_text: str,
    allowed_paths_text: str,
    signature: str,
) -> None:
    st.session_state.pop(REPAIR_REQUEST_KEY, None)
    try:
        if not repository_path.strip():
            raise RepoPilotServiceError("请填写本地 Git 仓库路径。")
        test_commands = _split_commands(test_commands_text)
        allowed_paths = _split_paths(allowed_paths_text)
        if not problem.strip():
            raise RepoPilotServiceError("请描述现象或粘贴完整报错。")
        if not test_commands:
            raise RepoPilotServiceError("请填写至少一条验证命令。")
        if not allowed_paths:
            raise RepoPilotServiceError("请填写允许修改的范围。")
        inspection = inspect_repository(Path(repository_path.strip()))
    except RepoPilotServiceError as exc:
        st.error(str(exc))
        return

    st.session_state[REPAIR_REQUEST_KEY] = {
        "signature": signature,
        "platform": platform,
        "problem": problem.strip(),
        "test_commands": test_commands,
        "allowed_paths": allowed_paths,
        "inspection": inspection,
    }


def _render_repair_preview(request: Mapping[str, Any], active_provider: Optional[ProviderConfig]) -> None:
    inspection = request["inspection"]
    if not isinstance(inspection, RepositoryInspection):
        st.error("修复预览已失效，请重新检查仓库。")
        return

    st.divider()
    st.markdown("#### 修复前确认")
    st.success("仓库检查通过。修复将在独立 worktree 中进行，原仓库不会被直接修改。")
    details = st.columns(3)
    details[0].metric("基准提交", inspection.head[:10])
    details[1].metric("当前分支", inspection.branch or "detached HEAD")
    details[2].metric("原仓库状态", "有未提交修改" if inspection.dirty else "干净")
    if inspection.dirty:
        st.warning("原仓库存在未提交修改；本次仍从上方固定提交创建隔离副本，不会覆盖这些修改。")
    if inspection.markers:
        st.caption(f"检测到项目文件：{', '.join(inspection.markers)}")

    st.markdown("##### 问题与验证方式")
    st.write(request["problem"])
    st.caption(VALIDATION_HINTS.get(str(request["platform"]), ""))
    st.code("\n".join(str(command) for command in request["test_commands"]), language="shell")
    st.markdown("##### 允许修改")
    st.code("\n".join(str(path) for path in request["allowed_paths"]), language="text")

    if active_provider is None:
        st.warning("请先在左侧配置并选择 AI Provider，才能开始定位和修复。")
        return
    st.caption(f"将使用当前 AI Provider：{active_provider.name} · {active_provider.model}")
    if st.button(
        "开始定位和修复",
        icon=":material/build:",
        type="primary",
        width="stretch",
        key="repopilot_repair_start",
    ):
        try:
            task_path = create_repair_task(
                inspection=inspection,
                platform=str(request["platform"]),
                problem=str(request["problem"]),
                test_commands=[str(item) for item in request["test_commands"]],
                allowed_paths=[str(item) for item in request["allowed_paths"]],
            )
            with st.spinner("正在定位代码、生成修复并运行验证..."):
                invocation = run_repository_task(
                    repository=inspection.root,
                    task=task_path,
                    runtime="pi",
                    strategy="focused",
                    keep_worktree=True,
                    pi_env=pi_environment(active_provider),
                )
        except RepoPilotServiceError as exc:
            st.error(str(exc))
        else:
            st.session_state[REPAIR_RESULT_KEY] = invocation
            st.rerun()


def _render_repair_result(invocation: CliInvocation) -> None:
    payload = to_evaluation_payload(invocation)
    artifacts = load_eval_artifacts(payload)
    if not artifacts:
        st.error(invocation.error or "修复任务未生成可读取的结果。")
        return
    artifact = artifacts[0]
    status = str(artifact.get("status") or "failed")
    verification = artifact.get("verification", {})
    checks = verification.get("checks", []) if isinstance(verification, dict) else []
    passed_checks = sum(1 for check in checks if check.get("ok"))
    changed_files = _changed_files(str(artifact.get("diff") or ""))

    st.divider()
    st.markdown("#### 修复结果")
    if status == "succeeded":
        st.success("修复已通过全部验证。请在隔离副本中查看 Diff，确认后再自行应用到原仓库。")
    else:
        failure = artifact.get("failure_category") or "验证未通过"
        st.error(f"本次修复尚未通过验证：{failure}。原仓库没有被修改。")
    summary = st.columns(4)
    summary[0].metric("验证", f"{passed_checks}/{len(checks)} 通过")
    summary[1].metric("修改文件", len(changed_files))
    summary[2].metric("工具调用", artifact.get("metrics", {}).get("tool_calls", 0))
    summary[3].metric("耗时", _duration_label(artifact.get("metrics", {}).get("duration_ms", 0)))

    worktree = str(artifact.get("worktree") or "")
    if worktree:
        st.markdown("##### 隔离副本")
        st.code(worktree, language="text")

    if checks:
        st.markdown("##### 验证结果")
        st.dataframe(
            [
                {"检查": check["name"], "状态": "通过" if check["ok"] else "未通过", "耗时 (ms)": check["duration_ms"]}
                for check in checks
            ],
            hide_index=True,
            width="stretch",
        )
        failed = [check for check in checks if check.get("output") and not check.get("ok")]
        if failed:
            st.markdown("##### 未通过的输出")
            selected = st.selectbox(
                "查看输出",
                range(len(failed)),
                format_func=lambda index: failed[index]["name"],
                key=f"repopilot_repair_failed_output_{artifact.get('run_id', 'unknown')}",
            )
            st.code(failed[selected]["output"], language="text")

    st.markdown("##### 代码修改")
    if changed_files:
        st.caption("已修改：" + "、".join(changed_files))
    diff = str(artifact.get("diff") or "")
    st.code(diff or "(没有留下可验证的代码修改)", language="diff")

    with st.expander("技术详情（上下文、Trace 与报告）", expanded=False):
        _render_run_technical_details(artifact)


def _render_bundled_evaluation(active_provider: Optional[ProviderConfig]) -> None:
    tasks = discover_tasks()
    suites = discover_suites()
    if not tasks or not suites:
        st.error("未发现内置任务或任务集。")
        return

    st.info("这些任务用于维护执行引擎；它们是确定性 fixture，不代表完整的 PX4、ArduPilot 或 ROS 上游评测。")
    source_col, runtime_col, strategy_col = st.columns([1.2, 1, 1.4])
    with source_col:
        source_kind = st.radio("执行范围", ["任务集", "单个任务"], horizontal=True, key="repopilot_fixture_source_kind")
    with runtime_col:
        runtime = st.selectbox("运行时", list(RUNTIME_LABELS), format_func=RUNTIME_LABELS.get, key="repopilot_fixture_runtime")
    with strategy_col:
        strategy = st.selectbox("上下文策略", list(STRATEGY_LABELS), format_func=STRATEGY_LABELS.get, key="repopilot_fixture_strategy")

    selected_suite = None
    selected_task = None
    if source_kind == "任务集":
        selected_suite = st.selectbox("任务集", suites, format_func=lambda item: item.label, key="repopilot_fixture_suite")
    else:
        selected_task = st.selectbox("任务", tasks, format_func=lambda item: item.label, key="repopilot_fixture_task")
        if selected_task.prompt:
            st.caption(selected_task.prompt)

    _render_pi_status(runtime, active_provider)
    if st.button("开始评测", icon=":material/play_arrow:", type="primary", key="repopilot_fixture_start"):
        try:
            process_env = _pi_environment_for(runtime, active_provider)
            with st.spinner("正在隔离执行并验证任务..."):
                invocation = run_evaluation(
                    suite=selected_suite.path if selected_suite else None,
                    task=selected_task.path if selected_task else None,
                    runtime=runtime,
                    strategy=strategy,
                    pi_env=process_env,
                )
        except RepoPilotServiceError as exc:
            st.error(str(exc))
        else:
            st.session_state[FIXTURE_RESULT_KEY] = invocation
            if invocation.payload is None:
                st.error(invocation.error or "评测未返回结果。")
            else:
                st.rerun()

    invocation = _stored_invocation(FIXTURE_RESULT_KEY)
    if invocation:
        _render_evaluation_result(invocation)


def _render_repository_evaluation(active_provider: Optional[ProviderConfig]) -> None:
    st.caption("供已有任务 YAML 的开发者使用。任务会在目标仓库的隔离 Git worktree 中执行。")
    st.warning("仅运行你信任的任务 YAML：任务可以声明 shell、测试和 setup 命令。")
    repository_path = st.text_input("Git 仓库路径", placeholder=r"D:\work\px4", key="repopilot_repository_path")
    task_path = st.text_input("任务 YAML 路径", placeholder=r"D:\work\tasks\fix-topic.yml", key="repopilot_repository_task_path")
    runtime_col, strategy_col, worktree_col = st.columns([1, 1.4, 1])
    with runtime_col:
        runtime = st.selectbox("运行时", list(RUNTIME_LABELS), format_func=RUNTIME_LABELS.get, key="repopilot_repository_runtime")
    with strategy_col:
        strategy = st.selectbox("上下文策略", list(STRATEGY_LABELS), format_func=STRATEGY_LABELS.get, key="repopilot_repository_strategy")
    with worktree_col:
        keep_worktree = st.checkbox("保留 worktree", value=True, key="repopilot_repository_keep_worktree")

    _render_pi_status(runtime, active_provider)
    if st.button("运行任务 YAML", icon=":material/play_arrow:", type="primary", key="repopilot_repository_start"):
        try:
            if not repository_path.strip() or not task_path.strip():
                raise RepoPilotServiceError("请填写 Git 仓库路径和任务 YAML 路径。")
            process_env = _pi_environment_for(runtime, active_provider)
            with st.spinner("正在隔离执行并验证任务..."):
                invocation = run_repository_task(
                    repository=Path(repository_path.strip()), task=Path(task_path.strip()), runtime=runtime,
                    strategy=strategy, keep_worktree=keep_worktree, pi_env=process_env,
                )
        except RepoPilotServiceError as exc:
            st.error(str(exc))
        else:
            st.session_state[REPOSITORY_RESULT_KEY] = invocation
            if invocation.payload is None:
                st.error(invocation.error or "任务未返回结果。")
            else:
                st.rerun()

    invocation = _stored_invocation(REPOSITORY_RESULT_KEY)
    if invocation:
        payload = to_evaluation_payload(invocation)
        if payload.get("tasks"):
            _render_evaluation_result(invocation, payload=payload)
        else:
            st.error(invocation.error or "任务未生成可读取的运行产物。")


def _render_pi_status(runtime: str, active_provider: Optional[ProviderConfig]) -> None:
    if runtime != "pi":
        return
    if active_provider is None:
        st.warning("Pi Agent 运行需要先在侧边栏选择 API Provider。")
    else:
        st.caption(f"Pi 使用当前 Provider：{active_provider.name} · {active_provider.model}")


def _pi_environment_for(runtime: str, active_provider: Optional[ProviderConfig]) -> Optional[dict[str, str]]:
    if runtime != "pi":
        return None
    if active_provider is None:
        raise RepoPilotServiceError("请先在侧边栏配置并选择 AI Provider。")
    return pi_environment(active_provider)


def _stored_invocation(key: str) -> Optional[CliInvocation]:
    invocation = st.session_state.get(key)
    return invocation if isinstance(invocation, CliInvocation) and invocation.payload is not None else None


def _render_evaluation_result(invocation: CliInvocation, *, payload: Optional[Mapping[str, Any]] = None) -> None:
    payload = dict(payload or invocation.payload or {})
    artifacts = load_eval_artifacts(payload)
    total = int(payload.get("total", len(artifacts)) or 0)
    succeeded = int(payload.get("succeeded", 0) or 0)
    success_rate = float(payload.get("successRate", 0) or 0)
    tool_calls = sum(item.get("metrics", {}).get("tool_calls", 0) for item in artifacts)
    duration_ms = sum(item.get("metrics", {}).get("duration_ms", 0) for item in artifacts)
    recovery_count = sum(item.get("metrics", {}).get("recovery_count", 0) for item in artifacts)
    tests_passed = sum(1 for item in artifacts if item.get("metrics", {}).get("test_passed"))

    st.divider()
    if invocation.error:
        st.warning(invocation.error)
    elif succeeded == total:
        st.success("评测完成，所有任务已通过验证。")
    else:
        st.warning("评测完成，存在未通过验证的任务。")
    metric_columns = st.columns(6)
    metric_columns[0].metric("任务", f"{succeeded}/{total}")
    metric_columns[1].metric("成功率", f"{success_rate * 100:.1f}%")
    metric_columns[2].metric("测试通过", f"{tests_passed}/{total}")
    metric_columns[3].metric("工具调用", tool_calls)
    metric_columns[4].metric("耗时", _duration_label(duration_ms))
    metric_columns[5].metric("恢复", recovery_count)

    report = Path(str(payload.get("report") or ""))
    if report.is_file():
        st.download_button("下载 HTML 报告", data=report.read_bytes(), file_name=report.name, mime="text/html", key=f"repopilot_report_{report.name}")
    rows = [
        {
            "任务": artifact.get("task_id"), "状态": artifact.get("status"),
            "测试": "通过" if artifact.get("metrics", {}).get("test_passed") else "未通过",
            "工具": artifact.get("metrics", {}).get("tool_calls", 0),
            "上下文 token": artifact.get("metrics", {}).get("context_tokens", 0),
            "文件": artifact.get("metrics", {}).get("selected_files", 0),
            "恢复": artifact.get("metrics", {}).get("recovery_count", 0),
            "耗时 (ms)": artifact.get("metrics", {}).get("duration_ms", 0),
            "失败分类": artifact.get("failure_category") or "-",
        }
        for artifact in artifacts
    ]
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    for artifact in artifacts:
        _render_run_details(artifact)


def _render_run_details(artifact: dict[str, Any]) -> None:
    title = f"{artifact.get('task_id', 'unknown')} · {artifact.get('status', 'unknown')}"
    with st.expander(title):
        _render_run_technical_details(artifact, include_diff=True)


def _render_run_technical_details(artifact: Mapping[str, Any], *, include_diff: bool = False) -> None:
    if artifact.get("unavailable"):
        st.warning("该运行产物已不可用。")
        return
    worktree = str(artifact.get("worktree") or "")
    if worktree:
        st.text(f"隔离 worktree：{worktree}")
    context = artifact.get("context", {})
    if not isinstance(context, Mapping):
        context = {}
    context_columns = st.columns(3)
    context_columns[0].metric("策略", context.get("strategy") or "-")
    context_columns[1].metric("上下文", f"{context.get('estimated_tokens', 0)}/{context.get('budget_tokens', 0)}")
    context_columns[2].metric("选中文件", len(context.get("selected_files", [])))
    selected_files = context.get("selected_files", [])
    if selected_files:
        st.code("\n".join(str(item) for item in selected_files), language="text")

    trace = artifact.get("trace", {})
    if not isinstance(trace, Mapping):
        trace = {}
    st.markdown("##### Trace")
    trace_columns = st.columns(4)
    trace_columns[0].metric("事件", trace.get("event_count", 0))
    trace_columns[1].metric("工具", trace.get("tool_calls", 0))
    trace_columns[2].metric("验证", trace.get("verification_events", 0))
    trace_columns[3].metric("恢复", trace.get("recovery_count", 0))
    timeline = trace.get("timeline", [])
    if timeline:
        st.dataframe(timeline, hide_index=True, width="stretch")

    replay_key = f"repopilot_replay_{artifact.get('run_id', 'unknown')}"
    if st.button("回放 Trace", icon=":material/replay:", key=replay_key):
        try:
            with st.spinner("正在读取 Trace..."):
                replay = replay_run(Path(str(artifact["run_dir"])))
        except RepoPilotServiceError as exc:
            st.error(str(exc))
        else:
            if replay.payload:
                st.json(replay.payload)
            else:
                st.error(replay.error or "Trace 回放失败。")

    if include_diff:
        st.markdown("##### 最终 Diff")
        st.code(str(artifact.get("diff") or "(无变更)"), language="diff")


def _repair_signature(platform: str, repository: str, problem: str, commands: str, scope: str) -> str:
    return "\x1f".join((platform, repository.strip(), problem.strip(), commands.strip(), scope.strip()))


def _split_commands(value: str) -> list[str]:
    return [item.strip() for item in value.splitlines() if item.strip()]


def _split_paths(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", "\n").splitlines() if item.strip()]


def _changed_files(diff: str) -> list[str]:
    files: list[str] = []
    for line in diff.splitlines():
        if not line.startswith("+++ b/"):
            continue
        path = line[6:]
        if path and path not in files:
            files.append(path)
    return files


def _duration_label(duration_ms: int) -> str:
    duration_ms = int(duration_ms or 0)
    if duration_ms < 1_000:
        return f"{duration_ms} ms"
    return f"{duration_ms / 1_000:.1f} s"
