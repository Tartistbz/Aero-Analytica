# RepoPilot Architecture

## Ownership boundary

Pi Agent is the model-facing execution loop. RepoPilot does not claim to implement a coding agent from scratch. It provides the surrounding harness that makes agent work in a repository bounded, inspectable and reproducible.

| Component | Owner | Responsibility |
|---|---|---|
| Agent loop and model turns | Pi SDK | Planning, tool selection, model streaming and Pi session state |
| Task lifecycle | RepoPilot | Run state, worktree creation, verification status and final outcome |
| Context Engine | RepoPilot | Repository map, file ranking, token budget and history compression |
| Repository tools | RepoPilot | Search, reads, unified patches, commands, tests and Git diff |
| Safety and recovery | RepoPilot | Worktree boundary, command filter, retries, checkpoint persistence and resume |
| Evidence | RepoPilot | JSONL trace, redaction, replay, reports and evaluation aggregation |

## Run lifecycle

```text
created -> preparing -> running -> verifying -> succeeded
                         |             |
                         v             v
                    checkpointed      failed
                         |
                         v
                      resumed
```

1. The task schema validates its base ref, acceptance gates and diff policy.
2. RepoPilot creates a detached worktree. Tool paths are resolved against that worktree.
3. The context engine writes `context.json` with the map, selected files, dropped files and estimated token usage.
4. Pi gets only the RepoPilot custom tools, the task prompt and the context package. Built-in Pi write and bash tools are disabled.
5. RepoPilot writes a checkpoint and JSONL events after every tool result.
6. The verifier runs declared tests, lint, assertions and Git diff policy checks.
7. The run is successful only if the Pi runtime completes and every verifier check passes.

## Artifact layout

```text
.repopilot/runs/<run-id>/
├─ metadata.json
├─ context.json
├─ events.jsonl
├─ checkpoint.json
├─ checkpoints/
├─ final.diff
└─ report.html
```

`events.jsonl` is append-only. It records runtime requests, tool calls, tool results, retry attempts, checkpoints, verification and the terminal status. Sensitive key names and common bearer-token forms are redacted before an event is written.

## Safety limits

- All file paths are resolved below the active worktree.
- Binary logs and fixture Git metadata are excluded from context discovery.
- Destructive commands such as `git reset --hard`, `git clean -f`, root-level removal and format commands are rejected.
- Shell and tests have a task-defined timeout and output cap.
- `network: disabled` adds opt-out proxy environment variables; it is a process-level guard, not a full network namespace. Docker or WSL isolation is the planned hard-isolation mode.
- Failed runs retain their worktree so `resume` can inspect or continue it. Successful worktrees are removed by default.

## Current limits

- The default isolation layer is Git worktree. Docker/WSL profiles are not yet implemented.
- The bundled 15-task suite is deterministic fixture coverage for the Harness. Upstream PX4, ArduPilot and ROS tasks should be added as separately pinned task sources before comparing models publicly.
- Pi configuration is supplied by Pi's own credential/model configuration or runtime environment variables; RepoPilot intentionally does not build another credential store.
