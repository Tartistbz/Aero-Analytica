# RepoPilot Demo

From the repository root, run:

```powershell
.\docs\demo\repopilot-demo.ps1
```

The script demonstrates the complete offline path:

1. A deterministic smoke evaluation runs through task YAML, fixture materialization, an isolated Git worktree, fake tool calls and verification.
2. The 15-task PX4/ArduPilot/ROS suite produces an HTML metrics report.
3. The newest run is replayed from JSONL without a model request or shell execution.

The generated reports live under `.repopilot/reports/`, which is intentionally ignored by Git. For a real Pi run, configure Pi credentials and use the `run --runtime pi` command described in [README_REPOPILOT.md](../../README_REPOPILOT.md).
