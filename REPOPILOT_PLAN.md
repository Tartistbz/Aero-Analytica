# RepoPilot 实施方案

> 基于 Pi Agent 的真实代码库执行、验证与评测 Harness
>
> 目标截止：2026-09-15 MVP

## 1. 结论与范围

这个方向可行，而且比把 Pi Agent 直接嵌入 Aero-Analytica 更贴合 Coding Agent 岗位。Pi 提供基础 Agent Loop；本项目的工程价值放在上下文工程、隔离执行、验证、恢复、Trace、Replay 和真实机器人代码任务评测上。

第一阶段不删除或重写现有 Aero-Analytica。当前 Python/Streamlit 应用继续作为：

- 可演示的无人机日志分析产品；
- PX4、ArduPilot、ROS 相关真实任务的领域素材；
- RepoPilot 的第一个被测代码库和任务来源。

RepoPilot 先以顶层独立 TypeScript 工程落地。MVP 通过后，再决定保留为 monorepo，或拆分为单独的 `RepoPilot` GitHub 仓库。这样既保留已有成果，又能证明新的 Coding Agent 系统能力。

## 2. MVP 必须交付的能力

### 2.1 执行

```text
repopilot run --repo <path> --task <task.yml>
```

- 读取任务 YAML；
- 在指定仓库创建独立 Git worktree；
- 生成上下文包；
- 调用 Pi Runtime；
- 执行工具调用并持续记录状态；
- 运行验证器；
- 输出运行摘要和最终 diff；
- 基础分支绝不被 Agent 直接修改。

### 2.2 六个基础工具

| 工具 | 最小行为 | 安全约束 |
|---|---|---|
| `search` | 在 worktree 内按 glob/regex 搜索 | 禁止越出 worktree，限制结果数 |
| `read` | 读取指定文件和行范围 | 限制单次字节数，拒绝二进制和越界路径 |
| `patch` | 应用统一 diff | 只允许 worktree，失败返回可观察错误 |
| `shell` | 执行任务允许的命令 | 超时、工作目录、环境变量和输出上限 |
| `test` | 执行任务声明的测试命令 | 独立超时，保存退出码和输出 |
| `git_diff` | 返回状态、diff stat 和完整 diff | 只读，支持文件数量/行数策略检查 |

工具返回统一结构：

```ts
type ToolResult = {
  ok: boolean;
  output: string;
  exitCode?: number;
  durationMs: number;
  error?: { code: string; message: string; retryable: boolean };
};
```

### 2.3 上下文工程

上下文模块必须输出可审计的选择结果，而不是只把整个仓库塞给模型：

1. 生成仓库地图：目录、语言、入口、测试、配置和 Git 状态；
2. 按任务关键词、依赖关系和最近修改记录给文件排序；
3. 在 token 预算内选择文件；
4. 超预算时按优先级压缩历史和文件内容；
5. 记录 `selected_files`、`dropped_files`、预算和估算 token；
6. 支持 `full`、`focused`、`map-only` 三种策略，供评测对照。

### 2.4 验证与恢复

任务只有同时满足以下条件才算成功：

- 指定测试命令通过；
- 指定 lint/typecheck 命令通过（如任务声明）；
- diff 符合允许路径、最大文件数、最大新增/删除行数；
- 任务完成条件中的文件或文本断言成立；
- Agent 没有修改基础分支、任务目录外文件或敏感文件。

恢复机制分三层：

- 工具层：可重试错误按指数退避重试，非幂等 patch 不自动重复；
- 运行层：每次工具调用后写 checkpoint，超时后保留 worktree 和状态；
- 任务层：`resume --run <run-id>` 从最后一个 checkpoint 继续，不重新执行已确认成功的步骤。

## 3. 建议目录结构

当前仓库保留已有 `app.py`、`src/`、`tests/`。新增内容如下：

```text
repopilot/
├─ package.json
├─ tsconfig.json
├─ vitest.config.ts
├─ src/
│  ├─ cli.ts                 # run/resume/replay/eval/report
│  ├─ config.ts              # 默认配置和 schema 校验
│  ├─ task/schema.ts         # Task YAML 类型与校验
│  ├─ context/
│  │  ├─ repo-map.ts         # 仓库地图
│  │  ├─ selector.ts         # 文件选择和 token 预算
│  │  └─ history.ts          # 对话/工具历史压缩
│  ├─ runtime/
│  │  ├─ runtime.ts          # AgentRuntime 接口
│  │  ├─ pi-adapter.ts        # Pi Agent 适配器
│  │  └─ fake-runtime.ts      # 离线测试用确定性 Runtime
│  ├─ tools/                 # search/read/patch/shell/test/git-diff
│  ├─ sandbox/
│  │  ├─ worktree.ts         # worktree 创建、清理和保留
│  │  └─ limits.ts            # 路径、时间、输出和网络限制
│  ├─ recovery/
│  │  ├─ checkpoint.ts
│  │  └─ retry.ts
│  ├─ verify/                # 测试、lint、断言、diff policy
│  ├─ trace/                 # JSONL writer、schema、redaction、replay
│  └─ eval/                  # 任务集运行和指标聚合
└─ tests/
   ├─ unit/
   ├─ integration/
   └─ fixtures/
evals/
├─ tasks/px4/
├─ tasks/ardupilot/
├─ tasks/ros/
└─ suites/smoke.yml
docs/
└─ architecture/repopilot.md
```

第一版不引入前端、不引入数据库、不引入多 Agent。Trace 先使用 JSONL，报告先生成终端摘要和静态 HTML。

## 4. 任务 YAML 契约

每个任务必须能被第三方复现，不能只写自然语言目标：

```yaml
id: px4-parser-missing-topic
repo: fixtures/px4-log-tools
base_ref: 4f2a1c7
prompt: 修复缺失 Topic 时解析器崩溃的问题，并补充回归测试。
setup:
  commands:
    - npm ci
context:
  strategy: focused
  budget_tokens: 12000
  include:
    - src/**
    - test/**
acceptance:
  test_commands:
    - npm test -- --run
  lint_commands:
    - npm run typecheck
  assertions:
    - file_exists: test/missing-topic.test.ts
  diff_policy:
    allowed_paths: [src/**, test/**]
    max_files_changed: 6
    max_added_lines: 240
    max_deleted_lines: 120
limits:
  timeout_seconds: 900
  max_retries: 2
  network: disabled
fault_injection:
  enabled: false
```

任务校验器要在 Agent 启动前拒绝缺少 `base_ref`、验收命令或 diff policy 的任务。

## 5. Runtime 与状态模型

不要重新实现 Pi 的通用循环。RepoPilot 定义自己的边界并适配 Pi：

```ts
interface AgentRuntime {
  start(input: RuntimeInput): Promise<RuntimeOutput>;
  resume(checkpoint: Checkpoint): Promise<RuntimeOutput>;
}
```

Pi 适配器负责把以下内容映射到 Pi：

- 系统提示和任务提示；
- 可用工具 schema；
- 工具执行结果；
- 中断、超时和恢复信号；
- token 使用和模型元数据。

RepoPilot 自己负责任务生命周期：

```text
created → preparing → running → verifying → succeeded
                         ↓           ↓
                    checkpointed   failed
                         ↓           ↓
                      resumed ← recoverable
```

每个运行都有不可变 `run_id`，状态文件至少包含任务 ID、仓库 ref、worktree 路径、当前步骤、重试次数、最后 checkpoint 和最终结果。

## 6. Trace、Replay 与报告

每个运行目录：

```text
.repopilot/runs/<run-id>/
├─ metadata.json
├─ events.jsonl
├─ checkpoints/
├─ context.json
├─ final.diff
└─ report.html
```

事件类型至少包括：`run_started`、`context_selected`、`model_request`、`tool_call`、`tool_result`、`checkpoint_saved`、`verification`、`run_finished`。

敏感信息处理要求：

- API key、Authorization header、环境变量值在写入 Trace 前脱敏；
- 默认不记录完整飞行日志内容；
- Trace 中保存路径、摘要、哈希和采样信息，不保存凭据；
- replay 模式只读取 JSONL，不调用模型、不执行 shell。

首版报告指标：

| 指标 | 定义 |
|---|---|
| task success rate | 满足全部验收条件的任务数 / 总任务数 |
| test pass rate | 测试命令最终通过的任务比例 |
| tool calls | 每任务及按工具类型统计 |
| wall time | 从 run_started 到 run_finished |
| recovery count | 重试、checkpoint resume、超时恢复次数 |
| context tokens | 选择上下文的估算 token 数 |
| diff size | 修改文件数、新增行、删除行 |
| failure category | context/tool/test/timeout/diff/runtime 等分类 |

## 7. 评测任务集

先准备 15 个固定 commit、固定验收命令的任务，达到 20 个后再扩大对照实验：

| 领域 | 数量 | 任务类型 |
|---|---:|---|
| PX4 | 5 | ULog 字段兼容、缺失 Topic、防崩溃、测试补全、单位/时间转换 |
| ArduPilot | 5 | 消息解析、字段别名、异常日志、回归测试、性能小修复 |
| ROS | 5 | launch/config 参数、topic 处理、节点测试、错误处理、文档/类型修复 |

任务质量要求：

- 每个任务有明确 bug 或小功能，不超过一个工作日的人力；
- 基础版本必须失败，目标版本通过；
- 验收测试不能只检查文件存在，至少包含行为断言；
- 任务仓库和 commit 固定，CI 不依赖未锁定的远程分支；
- 记录人工参考 patch，作为 diff 和行为对照，不把参考 patch 提供给 Agent。

首轮对照只改变上下文策略，保持任务、模型、温度、超时和工具完全一致：

1. `map-only`：只给仓库地图；
2. `focused`：地图加排序后的相关文件；
3. `focused+history`：再加入压缩后的历史和失败结果。

这样能证明上下文工程本身的收益，而不是只展示一张成功截图。

## 8. 分阶段实施计划

### 阶段 0：定稿与脚手架（8/18—8/20）

- 冻结 Task YAML、Trace JSONL、ToolResult、VerifierResult schema；
- 建立 `repopilot/` TypeScript 工程、Vitest 和 CLI 空命令；
- 选择 1 个 PX4 任务和 1 个 ArduPilot 任务作为 smoke case；
- 写架构图和一条本地可复现命令。

**出口条件：** `pnpm test` 通过，`pnpm repopilot --help` 可运行，任务 schema 能拒绝非法输入。

### 阶段 1：隔离执行与工具（8/21—8/27）

- 完成 worktree 创建、基础 ref 校验和清理策略；
- 实现六个工具及统一错误码；
- 接入 fake runtime，先跑通不调用模型的集成测试；
- 增加路径越界、超时、输出过大和 patch 失败测试。

**出口条件：** fake runtime 能在隔离 worktree 完成一个修改任务，基础分支无变化。

### 阶段 2：Pi 适配、上下文与验证（8/28—9/3）

- 实现 Pi adapter，保留 fake runtime 作为离线回归路径；
- 生成 repo map、相关文件排序和 token 预算选择；
- 接入测试、lint、断言和 diff policy；
- 输出成功、失败和拒绝执行三种明确结果。

**出口条件：** 至少 4 个任务可通过真实验收；未通过测试或越界修改不能被标记为成功。

### 阶段 3：恢复、Trace、Replay（9/4—9/10）

- 每个工具调用后保存 checkpoint；
- 实现可重试错误、超时终止和 `resume`；
- 实现 JSONL trace、敏感信息脱敏和静态 HTML 报告；
- 实现 `replay`，证明不发起模型请求、不执行 shell。

**出口条件：** 人为注入一次工具失败或超时后，任务可以从 checkpoint 继续；同一 Trace 可离线回放。

### 阶段 4：任务集、对照实验与交付（9/11—9/15）

- 完成 15 个任务和 smoke suite；
- 跑三种上下文策略，生成指标表和失败分类；
- 写中英文 README、架构图、局限性和演示脚本；
- 录制一次从 YAML 到 report 的完整演示；
- 冻结 beta tag，不把 API key、日志和运行目录提交到 Git。

**MVP 出口条件：** 一条命令可运行 smoke suite；每个任务有 Trace、最终 diff、验证结果和失败归因；报告能复现关键指标。

## 9. CLI 设计

```powershell
pnpm install
pnpm repopilot run --repo . --task evals/tasks/px4/missing-topic.yml
pnpm repopilot resume --run .repopilot/runs/<run-id>
pnpm repopilot replay --run .repopilot/runs/<run-id>
pnpm repopilot eval --suite evals/suites/smoke.yml --strategy focused
pnpm repopilot report --run .repopilot/runs/<run-id> --format html
```

每个命令都必须输出：运行 ID、状态、产物目录和下一步建议。错误信息要说明失败发生在哪个阶段、是否可恢复以及推荐的命令。

## 10. 测试与质量门禁

提交前必须通过：

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm eval:smoke
```

测试层次：

- 单元测试：schema、路径安全、排序、预算、重试、脱敏和 diff policy；
- 集成测试：fake runtime + 临时 Git 仓库 + 六工具；
- 故障测试：shell 超时、patch 冲突、测试失败、worktree 恢复；
- 真实任务测试：固定 commit 的 PX4/ArduPilot/ROS 任务；
- Replay 测试：Trace 回放结果与原运行摘要一致。

## 11. 风险与明确取舍

| 风险 | 处理方式 |
|---|---|
| Pi API 变化或不可用 | 先定义 `AgentRuntime`，使用 fake runtime 保证主流程可测 |
| Windows 环境缺少 Docker | worktree 作为默认隔离，Docker/WSL 作为增强模式 |
| 机器人仓库过大 | 固定浅克隆和 commit，任务上下文只取必要文件 |
| 模型成功率波动 | 评测记录随机种子、模型、策略和完整 Trace，不只看一次成功 |
| shell 破坏宿主机 | 默认 worktree、网络关闭、超时、命令 allowlist；高风险命令拒绝 |
| Trace 泄露密钥或日志 | 写入前统一 redaction，CI 扫描常见 token 模式 |
| 目标过大导致无法按期完成 | MVP 不做多 Agent、IDE、长期记忆、自动 PR、复杂 Web UI |

## 12. Git 与交付规则

- 当前 Aero-Analytica 功能继续在 `main` 保持可运行；
- RepoPilot 开发使用 `codex/repopilot-mvp` 分支；
- 每完成一个阶段提交一次，提交信息使用 `feat(repopilot): ...` 或 `test(repopilot): ...`；
- 不提交 `.repopilot/runs/`、API key、日志、worktree 和构建产物；
- 9/15 前只发布一个 beta，不在 MVP 阶段自动 push、自动开 PR 或自动发布；
- README 必须明确 Pi 负责的部分和 RepoPilot 自己实现的工程部分，避免声称从零实现 Agent Loop。

## 13. 最终对外表述

> RepoPilot 基于 Pi Agent 扩展真实代码库工程 Harness，面向 PX4、ROS 和 ArduPilot 任务，提供上下文选择、隔离执行、状态恢复、结果验证、Trace 回放和可复现评测。Pi 提供基础 Agent Loop；RepoPilot 负责让 Agent 在真实仓库中可控、可验证、可恢复、可比较地完成工程任务。

这句话应作为 README、简历项目描述和演示视频的统一定位。
