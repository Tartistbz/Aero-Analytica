# Aero-Analytica

**中文** | [English](README_EN.md)

Aero-Analytica 是一个面向 PX4、ArduPilot、ROS 与相关机器人项目的 AI 故障定位工作台。它把飞行日志、工程源码和自然语言问题放到同一个排障流程中：先提取可验证的证据，再让 AI 给出原因判断和下一步行动，而不是只返回一段泛化聊天内容。

项目基于 Streamlit 构建，面向飞行调试、故障排查和机器人软件维护。

## 面向的问题

- **飞行问题诊断**：上传 `.bin` 或 `.ulg`，用自然语言询问动力、高度、姿态、传感器等飞行问题，结合曲线和诊断报告定位原因。
- **代码问题修复**：选择 PX4、ArduPilot、ROS 或其他本地 Git 仓库，粘贴错误或描述问题，确认验证命令后由 AI 在隔离 worktree 中尝试修复并执行验证。

代码修复功能不会直接修改原仓库。每一次修复都固定当前 Git 提交，并在独立 worktree 中执行；只有测试、断言和修改范围全部符合要求，才会显示为通过。用户可查看最终 Diff 后自行应用修改。

底层执行由 **RepoPilot** 提供：它负责仓库上下文选择、Git worktree 隔离、受限工具、验证门禁、Checkpoint 和 Trace。RepoPilot 是实现组件，不是用户日常需要学习的工作流；CLI、Pi 配置和任务 YAML 的开发者说明见 [README_REPOPILOT.md](README_REPOPILOT.md)。

## AI 的核心创新

Aero-Analytica 的 AI 不是“上传文件后让模型自由发挥”，而是围绕无人机和机器人排障设计了一条可检查的证据链：

1. **结构感知的字段调度**：每份 `.bin` / `.ulg` 日志先扫描出真实存在的消息、Topic 和字段。Dispatcher 根据用户的问题选择相关信号，因此不同飞行控制器、固件版本和日志裁剪方式都能使用，不依赖固定字段模板。
2. **证据优先的诊断**：Analyst 接收字段统计、时间采样和用户问题，结合曲线生成“现象 - 证据 - 可能原因 - 建议动作”的报告。原始日志不直接发送给 Provider，结论可以回到具体曲线和时间段复核。
3. **模型与服务商解耦**：Provider 层统一 OpenAI Compatible、Anthropic Compatible 及国内/自建网关，模型可切换，字段选择和报告生成逻辑不随服务商改变。模型输出被截断时会自动续写，减少长诊断报告半途结束的问题。
4. **从诊断到修复的闭环**：当问题指向源码、测试或配置时，AI 可在隔离 Git worktree 中定位和修改，并运行用户确认的验证命令。原仓库不会被直接写入，用户始终能先看 Diff 再决定是否应用。
5. **人机协作而非黑盒自动化**：AI 只负责缩小搜索范围、解释证据和提出候选修复；字段、曲线、Provider、补丁和最终结论都可以由用户调整或复核，适合真实飞行调试中的不确定性。

这套设计的目标是把“我感觉飞机飞得不对”转化为可操作的问题：应该看哪些信号、异常从何时开始、哪些假设已被数据支持，以及下一步该检查参数、硬件还是代码。

## 功能特点

- **ArduPilot 与 PX4 支持**：解析 `.bin` 和 `.ulg`，支持 PX4 多实例 Topic。
- **动态字段发现**：界面只展示当前日志真实存在的消息和字段，不依赖固定分析页面。
- **AI 字段推荐**：根据自然语言问题，从日志字段清单中选择相关数据。
- **手动字段控制**：支持搜索、增删字段，以及单独显示或隐藏图表曲线。
- **交互式时序图**：支持双 Y 轴、范围滑块和飞行模式背景。
- **多 Provider 管理**：可保存、编辑、测试、删除并切换多个 AI Provider。
- **通用 API 协议**：支持 OpenAI Compatible 和 Anthropic Compatible 接口。
- **远程模型列表**：可从 Provider 获取模型，也可以手工指定模型名。
- **报告自动续写**：模型输出达到长度上限时，可自动继续生成未完成的报告。
- **安全上传存储**：日志按 SHA-256 内容哈希保存，同名文件不会相互覆盖。
- **隔离代码修复**：输入问题和验证命令即可生成内部修复任务，无需手写 YAML；可查看验证结果、最终 Diff 和保留的 worktree。

## 典型 AI 应用

- **动力不足**：输入“飞机有点小马拉大车”，AI 会优先关联电机输出、电池电压、电流、油门和姿态响应，帮助区分动力储备不足、限流和控制器输出受限。
- **高度或姿态异常**：输入“高度控制不稳定”或“降落时突然下坠”，AI 会从高度源、期望值、估计器状态和控制输出中挑选证据，并标出需要复核的时间段。
- **传感器/估计器故障**：输入报错或日志中的异常提示，AI 会把消息字段与时间序列对应起来，避免只根据一条文本告警下结论。
- **源码回归**：粘贴 PX4、ArduPilot 或 ROS 的编译/测试错误，AI 在隔离副本中定位相关文件，提出补丁并用测试结果说明修复是否成立。

## 界面预览

### 主界面

![Aero-Analytica 主界面](assets/screenshots/main-workspace.PNG)

### Provider 配置

![API Provider 配置](assets/screenshots/provider-configuration.PNG)

### 字段选择

![日志字段选择](assets/screenshots/field-selection.PNG)

### AI 诊断

![AI 诊断报告](assets/screenshots/ai-diagnostic-report.PNG)

## 工作流程

```text
上传 .bin / .ulg 日志
          |
          v
动态扫描消息、Topic 和字段
          |
          +-------------------+
          |                   |
     手动选择字段          AI 推荐字段
          |                   |
          +---------+---------+
                    |
                    v
          提取并对齐时序数据
                    |
          +---------+---------+
          |                   |
      Plotly 图表       统计摘要与时序采样
                              |
                              v
                         AI 诊断报告
```

AI 分析包含两个阶段：

1. **Dispatcher** 根据用户问题和当前日志字段清单选择相关字段。
2. **Analyst** 根据所选数据的统计摘要和时序采样生成诊断报告。

原始日志文件不会直接发送给 AI Provider。发送内容包括用户问题、字段清单、统计摘要和少量时序采样。

## 快速开始

### 环境要求

- Python 3.9 或更高版本
- 可访问的 AI API（可选；手动日志分析不需要）
- Node.js 20.6 或更高版本（仅“代码问题修复”需要）

### 安装与运行

```powershell
git clone <your-repository-url>
cd Aero-Analytica

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# 仅“代码问题修复”需要
npm install
python -m streamlit run app.py
```

启动后访问 <http://localhost:8501>。

## 使用方法

1. 在侧边栏上传 ArduPilot `.bin` 或 PX4 `.ulg` 日志。
2. 不使用 AI 时，直接打开字段选择器，搜索并选择需要绘制的字段。
3. 使用 AI 时，点击“配置 API”，选择 Provider 模板并填写 API Key、服务地址和模型。
4. 保存 Provider 后，在右侧输入飞行问题，例如“动力是否不足”或“高度控制是否稳定”。
5. AI 推荐的字段会显示在左侧，可继续手动增删字段或隐藏单条曲线。
6. 图表和统计数据准备完成后，右侧会生成分析报告。
7. 需要处理源码问题时，切换到“代码问题修复”，选择目标平台并填写本地 Git 仓库路径。
8. 粘贴完整报错、失败测试输出或复现步骤，并填写项目中实际可运行的验证命令，一行一个。
9. 确认默认或手动调整的允许修改范围，点击“检查并预览修复”。页面会显示固定提交、分支、原仓库状态、验证命令和修改范围。
10. 选择侧边栏中的 AI Provider，点击“开始定位和修复”。AI 只在隔离 worktree 中修改代码。
11. 查看测试结果和最终 Diff；通过后在隔离副本中复核，再自行将需要的修改应用到原仓库。
12. “开发者工具”中的内置任务、Fake Runtime、Trace 和任务 YAML 导入用于维护或评测，不是日常修复的必需步骤。

## Provider 配置

内置模板包括 OpenAI、Anthropic、DeepSeek、智谱 GLM、OpenRouter、通义千问、硅基流动和自定义 Provider。

每个 Provider 可以配置：

- 协议类型
- Base URL 和 API 端点
- API Key
- 模型及模型列表端点
- 自定义 Headers
- JSON Mode

Provider 配置保存在本机的 `.aero-analytica/providers.json`。该目录已被 `.gitignore` 排除，但 API Key 当前仍为本地明文保存，请只在可信设备上使用。

## 项目结构

```text
Aero-Analytica/
|-- app.py                         # Streamlit 应用入口
|-- README.md                      # 中文说明
|-- README_EN.md                   # English guide
|-- PROJECT_ARCHITECTURE.md        # 详细架构与数据流
|-- requirements.txt               # Python 依赖
|-- package.json                   # RepoPilot Node 依赖与命令
|-- assets/screenshots/            # 界面截图
|-- src/
|   |-- analyzer/                  # ArduPilot 与 PX4 解析器
|   |-- ai/                        # Provider、Agent 和提示词
|   |-- repopilot/                 # 仓库检查、内部修复任务生成和 RepoPilot CLI 桥接
|   |-- ui/                        # 界面、图表和交互控件
|   `-- log_uploads.py             # 上传校验与哈希存储
|-- repopilot/                     # 代码修复执行与验证引擎
|-- evals/                         # 开发者维护用 PX4 / ArduPilot / ROS 任务与任务集
`-- tests/                         # 离线单元测试
```

运行时日志保存在本地 `data/` 目录。该目录、飞行日志和 Provider 配置均不会被 Git 跟踪。

详细的模块职责、数据契约和调用流程见 [PROJECT_ARCHITECTURE.md](PROJECT_ARCHITECTURE.md)。

## 测试

测试不调用真实 AI 服务：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py src tests
npm run typecheck
npm test
npm run eval:smoke
```

当前 Python 测试覆盖日志上传、PX4 解析、Provider 协议、AI Agent、字段选择、图表和 RepoPilot 桥接层；TypeScript 测试覆盖 RepoPilot 的任务执行、恢复、上下文与隔离逻辑。

## 当前限制

- 对话历史目前只用于界面显示，尚未作为完整多轮上下文发送给模型。
- AI 使用统计摘要和采样数据，短时异常仍可能被采样过程遗漏。
- 上传目录尚无容量上限和自动清理策略。
- API Key 尚未接入操作系统凭据库。
- 当前没有数据或报告导出功能，也没有完整的 Streamlit 端到端测试。
- 代码修复必须提供适合当前仓库的验证命令；工具不会猜测并执行未知的完整构建流程。
- 隔离 worktree 保护原仓库，但当前不是 Docker 或操作系统级沙箱；只应选择可信的本地仓库和 Provider。

## 许可证

本项目使用 [GNU General Public License v3.0](LICENSE)。
