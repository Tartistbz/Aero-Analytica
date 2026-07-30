# Aero-Analytica

**中文** | [English](README_EN.md)

Aero-Analytica 是一个面向无人机飞行日志的交互式分析与 AI 辅助诊断工具。它支持 ArduPilot `.bin` 和 PX4 `.ulg` 日志，能够从日志中动态发现消息、Topic 和字段，将用户选择或 AI 推荐的数据对齐为时序图，并结合统计摘要生成诊断报告。

项目基于 Streamlit 构建，适合飞行调试、故障排查和日志数据探索。

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

## 界面预览

截图文件放入 `assets/screenshots/` 后会自动显示在以下位置。截图前请隐藏 API Key、私人服务地址、坐标和其他敏感飞行数据。

### 主界面

![Aero-Analytica 主界面](assets/screenshots/main-workspace.png)

### Provider 配置

![API Provider 配置](assets/screenshots/provider-configuration.png)

### 字段选择

![日志字段选择](assets/screenshots/field-selection.png)

### AI 诊断

![AI 诊断报告](assets/screenshots/ai-diagnostic-report.png)

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

### 安装与运行

```powershell
git clone <your-repository-url>
cd Aero-Analytica

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
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
|-- assets/screenshots/            # README 截图槽位
|-- src/
|   |-- analyzer/                  # ArduPilot 与 PX4 解析器
|   |-- ai/                        # Provider、Agent 和提示词
|   |-- ui/                        # 界面、图表和交互控件
|   `-- log_uploads.py             # 上传校验与哈希存储
`-- tests/                         # 离线单元测试
```

运行时日志保存在本地 `data/` 目录。该目录、飞行日志和 Provider 配置均不会被 Git 跟踪。

详细的模块职责、数据契约和调用流程见 [PROJECT_ARCHITECTURE.md](PROJECT_ARCHITECTURE.md)。

## 测试

测试不调用真实 AI 服务：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py src tests
```

当前包含 36 个单元测试，覆盖日志上传、PX4 解析、Provider 协议、AI Agent、字段选择和图表逻辑。

## 当前限制

- 对话历史目前只用于界面显示，尚未作为完整多轮上下文发送给模型。
- AI 使用统计摘要和采样数据，短时异常仍可能被采样过程遗漏。
- 上传目录尚无容量上限和自动清理策略。
- API Key 尚未接入操作系统凭据库。
- 当前没有数据或报告导出功能，也没有完整的 Streamlit 端到端测试。

## 许可证

本项目使用 [GNU General Public License v3.0](LICENSE)。
