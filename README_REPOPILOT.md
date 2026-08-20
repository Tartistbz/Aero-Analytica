# RepoPilot

[中文](README.md) | **English**

RepoPilot is a TypeScript harness for running, verifying, recovering and evaluating Pi Agent on repository tasks. Pi owns the agent loop. RepoPilot owns the engineering control plane around it: repository context selection, Git worktree isolation, constrained tools, verification gates, checkpoints, JSONL traces, replay and reproducible evaluation.

The existing Aero-Analytica Python application remains the user-facing UAV and robotics troubleshooting product in this repository. Its **代码问题修复 / Code Repair** Streamlit tab is the normal graphical entry point: it converts a platform, repository, problem description, validation commands, and allowed edit scope into an internal task, then calls this CLI. RepoPilot remains the execution backend and does not replace flight-log analysis.

## Architecture

```text
Task YAML -> Context Engine -> Pi Agent SDK -> Repository Tools
     |                                            |
     +-> Worktree / limits / checkpoint <---------+
                         |
                         v
                 Verifier -> Trace / Replay / Report
```

## Capabilities

- Isolated Git worktrees created from a declared base ref.
- Six bounded repository tools: `search`, `read`, `patch`, `shell`, `test`, `git_diff`.
- Path traversal protection, shell safety filtering, output limits and timeouts.
- Repository map, ranked file selection and token budgets with `map-only`, `focused` and `focused+history` strategies.
- Test, lint, assertion and diff-policy verification. A run succeeds only when the runtime and every verification gate succeed.
- Checkpoints after every tool call, retry for retryable tool failures and `resume` support.
- JSONL events with credential redaction, offline replay and static HTML reports.
- A reproducible 15-task PX4, ArduPilot and ROS fixture suite for harness regression testing.

## Install

```powershell
npm install
npm run typecheck
npm test
```

Node.js 20.6 or later is required. The project installs `@mariozechner/pi-coding-agent` and uses its SDK directly.

## Run a task

```powershell
npm run repopilot -- run --repo D:\path\to\git-repository --task task.yml --runtime pi --strategy focused --keep-worktree
```

The base repository is never modified. RepoPilot creates a detached worktree under `<repo>\.repopilot\worktrees\`, and writes artifacts under `<repo>\.repopilot\runs\<run-id>\`.

To run the same task through the deterministic offline runtime used by CI:

```powershell
npm run repopilot -- run --repo D:\path\to\git-repository --task evals\tasks\px4\topic-instance.yml --runtime fake
```

`fake_actions` are only executed by the fake runtime. The Pi SDK prompt contains the task, acceptance conditions and selected context, not fixture reference actions.

## Configure Pi

RepoPilot first uses Pi's configured credentials and models. The standard Pi configuration location is managed by Pi itself. A single OpenAI-compatible endpoint can also be supplied at runtime:

```powershell
$env:REPOPILOT_PI_PROVIDER = "my-provider"
$env:REPOPILOT_PI_MODEL = "my-coding-model"
$env:REPOPILOT_PI_BASE_URL = "https://example.invalid/v1"
$env:REPOPILOT_PI_API = "openai-completions"
$env:REPOPILOT_PI_API_KEY = "..."
npm run repopilot -- run --repo D:\path\to\git-repository --task task.yml --runtime pi
```

Supported API values are Pi API identifiers such as `openai-completions`, `openai-responses` and `anthropic-messages`. Runtime credentials are passed to Pi in memory and are redacted before Trace persistence.

## Aero-Analytica workspace

After `npm install`, start the Python application and open **代码问题修复**. The normal repair flow asks for a platform, local Git repository, error or reproduction steps, validation commands, and allowed edit paths. It checks and pins the repository HEAD, then creates an ignored internal task under `.repopilot/ui-tasks/`; users do not need to write task YAML.

- **Code Repair** uses Pi Agent through the currently selected Aero-Analytica Provider, including custom request headers. Its API key is not written to the internal task, Trace, report, or Git.
- **Developer Tools** contains **Bundled Evaluation** and **Import Task YAML**. **确定性 Fake** runs checked-in fixture actions without a model or API request; raw YAML is reserved for trusted developer-created tasks.

The normal repair result prioritizes verification output, final diff, and the retained worktree. Context details, Trace, replay, and reports are available as technical details. A Trace replay only reads the existing JSONL artifact; it never calls a model.

## Replay and reports

```powershell
npm run repopilot -- replay --run D:\path\to\repository\.repopilot\runs\<run-id>
npm run repopilot -- report --run D:\path\to\repository\.repopilot\runs\<run-id> --format html
```

`replay` only reads `events.jsonl`: it does not call a model or run shell commands.

## Evaluation

Run the smoke suite:

```powershell
npm run eval:smoke
```

Run all 15 PX4, ArduPilot and ROS fixture tasks and generate a report:

```powershell
npm run eval:robotics -- --report .repopilot\reports\robotics-15.html
```

The bundled fixture suite is a deterministic harness regression suite. Its tasks model UAV/robotics data-handling concerns, but it is not represented as a benchmark of unmodified upstream PX4, ArduPilot or ROS repositories. External repository tasks use the same YAML format and must pin their `base_ref` and explicit acceptance gates.

## Task contract

```yaml
id: px4-timestamp-units
base_ref: 4f2a1c7
prompt: Fix the ULog timestamp conversion from microseconds to seconds.
context:
  strategy: focused
  budget_tokens: 12000
  include: [src/**, test/**]
acceptance:
  test_commands: [npm test -- --run]
  lint_commands: [npm run typecheck]
  assertions:
    - file_exists: test/timestamp.test.ts
  diff_policy:
    allowed_paths: [src/**, test/**]
    max_files_changed: 6
    max_added_lines: 240
    max_deleted_lines: 120
limits:
  timeout_seconds: 900
  max_retries: 2
  network: disabled
```

See [REPOPILOT_PLAN.md](REPOPILOT_PLAN.md) for the detailed implementation plan and [docs/architecture/repopilot.md](docs/architecture/repopilot.md) for runtime boundaries.
