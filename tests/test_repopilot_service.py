import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.ai.providers import (
    ANTHROPIC_COMPATIBLE,
    OPENAI_COMPATIBLE,
    ProviderConfig,
)
from src.repopilot.service import (
    CliInvocation,
    RepositoryInspection,
    create_repair_task,
    discover_suites,
    discover_tasks,
    load_run_artifact,
    pi_environment,
    run_evaluation,
    run_repository_task,
    to_evaluation_payload,
)


class RepoPilotServiceTests(unittest.TestCase):
    def test_checked_in_tasks_and_suites_are_discovered(self):
        tasks = discover_tasks()
        suites = discover_suites()

        self.assertEqual(len(tasks), 15)
        self.assertEqual(tasks[0].domain, "ARDUPILOT")
        self.assertEqual({suite.path.stem for suite in suites}, {"robotics-15", "smoke"})

    def test_openai_provider_is_translated_for_pi_process(self):
        provider = ProviderConfig(
            id="local",
            name="Local",
            template_id="custom_openai",
            protocol=OPENAI_COMPATIBLE,
            base_url="https://example.test/v1",
            endpoint="chat/completions",
            api_key="test-key",
            model="test-model",
            custom_headers={"X-Route": "uav"},
        )

        environment = pi_environment(provider)

        self.assertEqual(environment["REPOPILOT_PI_API"], "openai-completions")
        self.assertEqual(environment["REPOPILOT_PI_MODEL"], "test-model")
        self.assertEqual(environment["REPOPILOT_PI_API_KEY"], "test-key")
        self.assertEqual(environment["REPOPILOT_PI_HEADERS"], '{"X-Route": "uav"}')

    def test_anthropic_provider_is_translated_for_pi_process(self):
        provider = ProviderConfig(
            id="anthropic",
            name="Anthropic",
            template_id="custom_anthropic",
            protocol=ANTHROPIC_COMPATIBLE,
            base_url="https://api.anthropic.test",
            endpoint="v1/messages",
            api_key="test-key",
            model="claude-test",
        )

        self.assertEqual(
            pi_environment(provider)["REPOPILOT_PI_API"], "anthropic-messages"
        )

    def test_eval_invocation_parses_result_without_exposing_environment_key(self):
        root = Path(__file__).resolve().parents[1]
        suite = root / "evals" / "suites" / "smoke.yml"
        completed = SimpleNamespace(
            returncode=0,
            stdout='npm output\n{"total": 1, "succeeded": 1, "tasks": []}',
            stderr="",
        )

        with patch("src.repopilot.service.subprocess.run", return_value=completed) as run:
            result = run_evaluation(
                suite=suite,
                runtime="pi",
                pi_env={"REPOPILOT_PI_API_KEY": "do-not-display"},
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.payload["succeeded"], 1)
        self.assertNotIn("do-not-display", result.stdout)
        self.assertEqual(
            run.call_args.kwargs["env"]["REPOPILOT_PI_API_KEY"], "do-not-display"
        )

    def test_eval_invocation_reads_outer_object_when_tasks_are_nested(self):
        root = Path(__file__).resolve().parents[1]
        suite = root / "evals" / "suites" / "smoke.yml"
        payload = {
            "total": 1,
            "succeeded": 1,
            "tasks": [{"id": "px4-sample", "status": "succeeded"}],
        }
        completed = SimpleNamespace(
            returncode=0,
            stdout=f"npm output\n{json.dumps(payload, indent=2)}\n",
            stderr="",
        )

        with patch("src.repopilot.service.subprocess.run", return_value=completed):
            result = run_evaluation(suite=suite)

        self.assertEqual(result.payload, payload)

    def test_repository_run_uses_argument_array_and_keeps_worktree(self):
        root = Path(__file__).resolve().parents[1]
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "runId": "run-1",
                    "status": "succeeded",
                    "runDir": "D:/runs/run-1",
                    "worktree": "D:/repo/.repopilot/worktrees/run-1",
                }
            ),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repository = temp_root / "repository"
            repository.mkdir()
            (repository / ".git").mkdir()
            task = temp_root / "task.yml"
            task.write_text("id: sample\n", encoding="utf-8")

            with patch(
                "src.repopilot.service.subprocess.run", return_value=completed
            ) as run:
                result = run_repository_task(
                    repository=repository,
                    task=task,
                    runtime="pi",
                    strategy="focused+history",
                    keep_worktree=True,
                    pi_env={"REPOPILOT_PI_API_KEY": "do-not-display"},
                    root=root,
                )

        command = run.call_args.args[0]
        self.assertTrue(result.ok)
        self.assertIn("run", command)
        self.assertIn("--keep-worktree", command)
        self.assertIn("focused+history", command)
        self.assertNotIn("do-not-display", command)

    def test_repair_form_creates_a_bounded_internal_task(self):
        inspection = RepositoryInspection(
            root=Path("D:/robotics/repository"),
            head="a" * 40,
            branch="main",
            dirty=False,
            markers=("package.xml",),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            task_path = create_repair_task(
                inspection=inspection,
                platform="ROS / ROS 2",
                problem="node crashes when a topic is missing",
                test_commands=["colcon test --packages-select telemetry"],
                allowed_paths=["src/**", "test/**"],
                root=Path(temp_dir),
            )
            payload = json.loads(task_path.read_text(encoding="utf-8"))

        self.assertTrue(task_path.is_relative_to(Path(temp_dir) / ".repopilot"))
        self.assertEqual(payload["base_ref"], "a" * 40)
        self.assertEqual(payload["acceptance"]["test_commands"], ["colcon test --packages-select telemetry"])
        self.assertEqual(payload["acceptance"]["diff_policy"]["allowed_paths"], ["src/**", "test/**"])
        self.assertEqual(payload["limits"]["network"], "disabled")
        self.assertNotIn("fake_actions", payload)

    def test_run_artifact_includes_trace_and_verifier_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            (run_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "runId": "run-1",
                        "taskId": "px4-sample",
                        "worktree": "D:/repo/.repopilot/worktrees/run-1",
                        "status": "succeeded",
                        "verification": {
                            "ok": True,
                            "checks": [
                                {
                                    "name": "test:node",
                                    "ok": True,
                                    "durationMs": 12,
                                    "output": "ok",
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "context.json").write_text(
                json.dumps(
                    {
                        "strategy": "focused",
                        "estimatedTokens": 120,
                        "budgetTokens": 500,
                        "selectedFiles": ["src/sample.js"],
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "events.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"timestamp": "t1", "type": "tool_call"}),
                        json.dumps(
                            {
                                "timestamp": "t2",
                                "type": "run_finished",
                                "payload": {"status": "succeeded"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "final.diff").write_text("diff --git a/a b/a", encoding="utf-8")

            artifact = load_run_artifact(run_dir)
            payload = to_evaluation_payload(
                CliInvocation(
                    command=("npm", "run"),
                    returncode=0,
                    duration_ms=42,
                    payload={
                        "runId": "run-1",
                        "status": "succeeded",
                        "runDir": str(run_dir),
                    },
                    stdout="",
                    stderr="",
                )
            )

        self.assertTrue(artifact["verification"]["ok"])
        self.assertEqual(artifact["trace"]["tool_calls"], 1)
        self.assertEqual(artifact["context"]["selected_files"], ["src/sample.js"])
        self.assertEqual(artifact["worktree"], "D:/repo/.repopilot/worktrees/run-1")
        self.assertEqual(payload["tasks"][0]["toolCalls"], 1)
        self.assertTrue(payload["tasks"][0]["testPassed"])


if __name__ == "__main__":
    unittest.main()
