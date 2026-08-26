# Aero-Analytica

[中文](README.md) | **English**

Aero-Analytica is an AI troubleshooting workbench for PX4, ArduPilot, ROS, and related robotics projects. It brings flight logs, source code, and natural-language questions into one workflow: extract checkable evidence first, then ask AI to explain causes and next actions instead of returning a generic chat response.

The application is built with Streamlit for flight debugging, troubleshooting, and robotics software maintenance.

## Problems It Solves

- **Flight diagnosis**: Upload a `.bin` or `.ulg` file, ask about propulsion, altitude, attitude, or sensors, then investigate the relevant curves and AI diagnostic report.
- **Code repair**: Choose a PX4, ArduPilot, ROS, or other local Git repository; paste an error or describe a failure; confirm validation commands; then let AI attempt a verified repair in an isolated worktree.

Code repair never writes directly to the original repository. Each run pins the current Git commit and operates in a separate worktree. A repair is marked successful only when its tests, assertions, and edit-scope policy all pass. Review the final diff, then apply the desired changes yourself.

The internal execution component is **RepoPilot**. It provides repository-context selection, Git worktree isolation, constrained tools, verification gates, checkpoints, and Trace artifacts. It is not a workflow that normal users need to learn. Its developer CLI, Pi configuration, and task-YAML reference are in [README_REPOPILOT.md](README_REPOPILOT.md).

## AI Innovation

Aero-Analytica does not simply upload a log and let a model guess. It is built around an evidence chain for UAV and robotics troubleshooting:

1. **Schema-aware field dispatch**: Every `.bin` / `.ulg` file is scanned for the messages, topics, and fields that actually exist. The Dispatcher selects signals relevant to the user's question, so the workflow remains useful across controllers, firmware versions, and trimmed logs without a fixed field template.
2. **Evidence-first diagnosis**: The Analyst receives field statistics, time-series samples, and the user's question, then produces a report structured around observed behavior, evidence, likely causes, and recommended actions. Raw logs are not sent directly to the Provider, and every conclusion can be checked against a curve and time range.
3. **Provider and model portability**: A single Provider layer supports OpenAI Compatible, Anthropic Compatible, domestic services, and self-hosted gateways. Models can be switched without changing the diagnosis workflow. Truncated model output is continued automatically so long reports do not end mid-sentence.
4. **A diagnosis-to-repair loop**: When evidence points to source, test, or configuration issues, AI can inspect and patch an isolated Git worktree and run validation commands confirmed by the user. The original repository is never written directly; users review the diff before applying it.
5. **Human-guided, not black-box automation**: Users can adjust fields, curves, Providers, patches, and conclusions. AI narrows the search space and explains evidence, while the engineer remains in control of decisions and verification.

The goal is to turn “the aircraft feels wrong” into an actionable investigation: which signals to inspect, when the anomaly began, which hypotheses the data supports, and whether the next check belongs to parameters, hardware, or code.

## Features

- **ArduPilot and PX4 support**: Parse `.bin` and `.ulg` logs, including multi-instance PX4 topics.
- **Dynamic field discovery**: Show only the messages and fields that exist in the current log.
- **AI field recommendation**: Select relevant data from the log schema based on a natural-language question.
- **Manual field control**: Search, add, remove, show, or hide individual chart series.
- **Interactive time-series charts**: Use dual Y axes, a range slider, and flight-mode backgrounds.
- **Multiple Provider management**: Save, edit, test, delete, and switch between AI Providers.
- **Common API protocols**: Connect to OpenAI Compatible and Anthropic Compatible endpoints.
- **Remote model discovery**: Fetch models from a Provider or enter a model name manually.
- **Automatic report continuation**: Continue an incomplete report when a model reaches its output limit.
- **Content-addressed uploads**: Store logs by SHA-256 hash so same-named files cannot overwrite one another.
- **Isolated code repair**: Enter a problem and validation commands to create a bounded internal repair task without writing YAML; inspect verification, final diff, and the retained worktree.

## Typical AI Use Cases

- **Insufficient thrust**: Ask “the aircraft feels underpowered.” AI prioritizes motor output, battery voltage/current, throttle, and attitude response to distinguish limited power reserve, current limiting, and controller saturation.
- **Altitude or attitude instability**: Ask “altitude control is unstable” or “it drops during landing.” AI selects altitude sources, setpoints, estimator state, and control outputs, then highlights time ranges worth reviewing.
- **Sensor or estimator faults**: Paste an alert or log message. AI links the message fields to the corresponding time series instead of treating a single text warning as a complete diagnosis.
- **Source regressions**: Paste a PX4, ArduPilot, or ROS build/test failure. AI locates the relevant files in an isolated copy, proposes a patch, and uses test results to show whether the fix holds.

## Screenshots

### Main Workspace

![Aero-Analytica main workspace](assets/screenshots/main-workspace.PNG)

### Provider Configuration

![API Provider configuration](assets/screenshots/provider-configuration.PNG)

### Field Selection

![Flight-log field selection](assets/screenshots/field-selection.PNG)

### AI Diagnostics

![AI diagnostic report](assets/screenshots/ai-diagnostic-report.PNG)

## Workflow

```text
Upload a .bin / .ulg log
           |
           v
Discover messages, topics, and fields
           |
           +--------------------+
           |                    |
    Manual selection       AI recommendation
           |                    |
           +----------+---------+
                      |
                      v
          Extract and align time-series data
                      |
           +----------+----------+
           |                     |
      Plotly charts      Statistics and samples
                                 |
                                 v
                         AI diagnostic report
```

AI analysis has two stages:

1. The **Dispatcher** selects relevant fields from the current log schema and user question.
2. The **Analyst** generates a report from statistics and sampled time-series rows.

Raw log files are not sent directly to the AI Provider. The request includes the user question, field schema, statistical summary, and a small time-series sample.

## Quick Start

### Requirements

- Python 3.9 or later
- Access to an AI API is optional; manual log analysis works without one
- Node.js 20.6 or later is required only for Code Repair

### Install and Run

```powershell
git clone <your-repository-url>
cd Aero-Analytica

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Required only for Code Repair
npm install
python -m streamlit run app.py
```

Open <http://localhost:8501> after startup.

## Usage

1. Upload an ArduPilot `.bin` or PX4 `.ulg` log from the sidebar.
2. For manual analysis, open the field selector and search for the data to plot.
3. For AI analysis, select **Configure API**, choose a Provider template, and enter the API key, endpoint, and model.
4. Save the Provider, then ask a flight-related question such as "Is the aircraft underpowered?" or "Was altitude control stable?"
5. AI-recommended fields appear on the left, where fields can still be added, removed, or hidden individually.
6. After chart data is prepared, the diagnostic report appears on the right.
7. To handle a source-code issue, open **Code Repair**, choose the target platform, and enter the local Git repository path.
8. Paste the complete error, failing-test output, or reproduction steps. Enter the repository's real validation commands, one per line.
9. Confirm or adjust the allowed edit scope, then select **Check and Preview Repair**. The page shows the pinned commit, branch, original repository state, validation commands, and allowed paths.
10. Select an AI Provider in the sidebar and start repair. AI edits only an isolated worktree.
11. Inspect test results and the final diff. After a successful run, review the retained worktree and apply the selected changes to the original repository yourself.
12. The bundled tasks, Fake runtime, Trace, and raw task-YAML import under **Developer Tools** are for maintenance and evaluation, not routine repair.

## Provider Configuration

Built-in templates include OpenAI, Anthropic, DeepSeek, Zhipu GLM, OpenRouter, Qwen, SiliconFlow, and a custom Provider.

Each Provider can configure:

- Protocol type
- Base URL and API endpoint
- API key
- Model and model-list endpoint
- Custom headers
- JSON Mode

Provider state is stored locally in `.aero-analytica/providers.json`. The directory is excluded by `.gitignore`, but API keys are currently stored as plaintext on the local machine. Use the application only on a trusted device.

## Project Structure

```text
Aero-Analytica/
|-- app.py                         # Streamlit entry point
|-- README.md                      # Chinese guide
|-- README_EN.md                   # English guide
|-- PROJECT_ARCHITECTURE.md        # Detailed architecture and data flow
|-- requirements.txt               # Python dependencies
|-- package.json                   # RepoPilot Node dependencies and commands
|-- assets/screenshots/            # UI screenshots
|-- src/
|   |-- analyzer/                  # ArduPilot and PX4 parsers
|   |-- ai/                        # Providers, Agent, and prompts
|   |-- repopilot/                 # Repository preflight, internal task generation, and RepoPilot CLI bridge
|   |-- ui/                        # UI, charts, and controls
|   `-- log_uploads.py             # Upload validation and hash storage
|-- repopilot/                     # Code-repair execution and verification engine
|-- evals/                         # Developer-maintenance PX4 / ArduPilot / ROS tasks and suites
`-- tests/                         # Offline unit tests
```

Runtime logs are stored in the local `data/` directory. This directory, flight logs, and Provider configuration are not tracked by Git.

See [PROJECT_ARCHITECTURE.md](PROJECT_ARCHITECTURE.md) for module responsibilities, data contracts, and request flows.

## Testing

The test suite does not call a real AI service:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py src tests
npm run typecheck
npm test
npm run eval:smoke
```

Python tests cover upload storage, PX4 parsing, Provider protocols, the AI Agent, field selection, charts, and the RepoPilot bridge. TypeScript tests cover RepoPilot execution, recovery, context, and isolation.

## Current Limitations

- Chat history is currently display-only and is not sent as complete multi-turn context.
- AI analysis uses statistics and sampled rows, so short transient events may be missed.
- The upload directory has no size limit or automatic cleanup policy.
- API keys are not yet stored in an operating-system credential manager.
- Data export, report export, and full Streamlit end-to-end tests are not implemented.
- Code repair requires validation commands appropriate for the selected repository; the application does not guess and run an unknown full build.
- An isolated worktree protects the original repository, but it is not a Docker or operating-system-level sandbox. Use only trusted local repositories and Providers.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
