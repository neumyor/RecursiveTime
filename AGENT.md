# AGENT 操作规范

本项目是一个基于 Claude Code SDK 的时间序列 tool-use harness。它不是 research agent；核心目标是让 agent 更可靠地结合背景知识、数据证据和工具集来完成时间序列问题求解。

## 文档同步要求（强制）

`AGENT.md` 和 `README.md` 是面向 agent、用户和后续维护者的入口规范，必须与代码、prompt、CLI、配置保持一致。任何一次涉及以下范围的改动，**都必须**在同一个 commit（或紧随其后的 commit）里检查并同步 `README.md` 和 `AGENT.md`：

- Node chain 增删、节点 `phase/purpose/next` 变化、节点 spec / guidance 重大改写
- CLI 子命令、参数、flag 增删（`backend/harnessing_ts/cli.py`）
- MCP 工具集（`backend/harnessing_ts/mcp/server.py`）增删、schema 变更
- node native 工具白名单（`backend/harnessing_ts/config/nodes/<node>/native-tools.md`）
- 关键 prompt 模板（`backend/harnessing_ts/config/prompts/`、`backend/harnessing_ts/variants/prompts/`）
- 控制模式（`TS_HARNESS_CONTROL_MODE`）、消融变体（`TS_HARNESS_VARIANT`）、dry-run / debug / max-turns / workspace 等环境变量
- LLM 配置字段（`backend/harnessing_ts/settings/llm.py`、`config.llm.example.json`）
- 运行时记录 / 工作区布局 / `.gitignore` 变化
- 新增/废弃的运行命令、启动入口、Web UI 端口

任何 commit 前都必须执行文档一致性检查：用 `git diff -- README.md AGENT.md docs/` 复核用户文档和 agent 规范是否已经同步。只要改动影响行为、命令、配置、节点协议、运行产物、UI 操作或维护流程，就必须同步更新 `README.md` 和 `AGENT.md`；如果确认无需文档变更，需要在 commit message 中显式说明 `no doc change required: ...`，否则视为遗漏。

## 项目入口

本项目后端使用 Python 实现，依赖由 `uv` 管理。前端是 `frontend/` 下的静态页面，直接由 Python FastAPI 服务托管。

新服务器的标准流程必须优先保持为三条主命令：

```bash
git clone https://github.com/neumyor/RecursiveTime.git && cd RecursiveTime
uv run ts-harness setup-server
HOST=0.0.0.0 PORT=4327 TS_HARNESS_WORKSPACE=/srv/harnessingts/workspaces/v0 TS_HARNESS_VARIANT=V0 uv run ts-harness-server
```

`uv run` 会先自动同步 Python 后端；`setup-server` 会继续执行 frozen Bun install、生产前端构建和共享 runtime base 构建；`ts-harness-server` 会在首次启动时自动创建并初始化 `TS_HARNESS_WORKSPACE`。不要再要求用户重复执行 `uv sync`、`bun install/build`、`prepare-runtime-base` 和 `ts-harness init`。

以下拆分命令只用于开发、诊断或局部重建：

```bash
uv sync
uv run ts-harness prepare-runtime-base
uv run ts-harness init
```

发送主会话消息：

```bash
uv run ts-harness send "请基于 ECG5000 设计异常样本分类的工具使用流程"
```

Dry-run 状态流转：

```bash
uv run ts-harness --dry-run init
uv run ts-harness --dry-run start-node problem-contract --input-summary "ECG5000 abnormal sample classification"
uv run ts-harness --dry-run finish-node --summary "Wrote user/problem-contract.md and user/data-spec.md" --goal-met true --output-path user/problem-contract.md --output-path user/data-spec.md
```

Python 语法检查：

```bash
uv run python -m compileall backend/harnessing_ts
```

本地启动前端工作台：

```bash
uv run ts-harness-server
```

默认地址：

```text
http://127.0.0.1:4327
```

服务器部署并允许其他电脑访问时，必须显式绑定非 loopback 地址：

```bash
HOST=0.0.0.0 PORT=4327 TS_HARNESS_WORKSPACE=/srv/harnessingts/workspaces/v0 TS_HARNESS_VARIANT=V0 uv run ts-harness-server
```

对外共享部署必须先运行 `setup-server` 生成 `frontend/dist/` 和 runtime base，并在 README 的 “Deploy On A Server” 章节同步维护防火墙、进程守护、反向代理和安全注意事项。不要在公网部署时启用 `TS_HARNESS_DEBUG`。

不调用模型的前端测试模式：

```bash
TS_HARNESS_DRY_RUN=true uv run ts-harness-server
```

启用前端调试按钮，包括清空当前聊天记录：

```bash
TS_HARNESS_DEBUG=true uv run ts-harness-server
```

消融实验通过启动环境变量选择，默认 `V0`：

```bash
TS_HARNESS_VARIANT=V4 uv run ts-harness-server
```

变体定义、V2 固定随机目录和独立 prompt overlay 位于 `backend/harnessing_ts/variants/`。新增或修改消融行为时优先保持差异在该目录内，并通过 capability、工具权限和后端契约实施，不要只依赖 prompt 声明。变体只在进程启动时解析，不得新增运行时切换 API；不同实验应使用不同 `TS_HARNESS_WORKSPACE`。

## LLM 配置

默认使用 Claude Code SDK 的本机登录态。如果运行时显示 `not login`，可以改用手动 API 配置。

本地创建：

```bash
cp config.llm.example.json config.llm.json
```

DashScope Anthropic-compatible 示例：

```json
{
  "authMode": "manual",
  "protocol": "anthropic",
  "model": "qwen3.6-plus",
  "baseUrl": "https://dashscope.aliyuncs.com/api/v2/apps/anthropic",
  "apiKey": "YOUR_API_KEY",
  "contextWindow": "200k"
}
```

`config.llm.json` 已加入 `.gitignore`，不要提交真实 key。

也可以用环境变量：

```bash
export TS_HARNESS_LLM_AUTH_MODE=manual
export TS_HARNESS_LLM_PROTOCOL=anthropic
export TS_HARNESS_LLM_MODEL=qwen3.6-plus
export TS_HARNESS_LLM_BASE_URL=https://dashscope.aliyuncs.com/api/v2/apps/anthropic
export TS_HARNESS_LLM_API_KEY=YOUR_API_KEY
```

检查 SDK 实际注入配置：

```bash
uv run ts-harness llm-config
```

## Agent Lightning

训练能力是可选依赖，不参与普通后端启动。需要 APO/RL/SFT 闭环时安装：

```bash
uv sync --extra training
```

生成起始训练脚手架：

```bash
uv run ts-harness training-template
```

## 架构边界

- Claude Code SDK 是唯一 runtime 绑定。
- 后端代码必须放在 `backend/harnessing_ts/`；不要重新引入 Bun/TypeScript 后端。
- 前端代码必须放在 `frontend/`。
- 示例、训练脚手架和非运行时代码放在 `examples/`。
- 本地 JSONL 和文件系统是真相源。
- SDK session 是短命执行载体。
- Prompt / node spec 表达方法论。
- MCP 只做结构化状态突变和审计记录。
- `toolset` 描述 agent 可调用能力，不描述方法排行榜。
- `solution` 描述工具使用协议，不描述最佳模型。
- 训练只是让某些工具可用的实现细节，不是系统目标。

## 当前代码架构

后端采用“薄入口 + 应用编排 + 文件型基础设施”的结构。维护时应保持以下边界：

- `backend/harnessing_ts/server.py`：FastAPI 装配入口，负责路由注册、后台 task 启停和静态前端托管；不要在这里新增业务规则。
- `backend/harnessing_ts/api/payloads.py`：`/api/bootstrap`、`/api/live` 等前端聚合响应的组装层，负责稳定 HTTP contract。
- `backend/harnessing_ts/orchestrator.py`：应用编排 facade，协调主会话、node session、workspace store、知识服务和 runner 生命周期。
- `backend/harnessing_ts/node_state.py`：node chain 状态机、`loopDecision` / `nextNode` 校验、pipeline 完成判断、variant-aware iterative-solving 输出路径约束和 V6 one-shot 强制停止。
- `backend/harnessing_ts/variants/profiles.py`：V0-V7 profile、capability、节点 purpose/input/output override 和 overlay 路由的单一事实源。
- `backend/harnessing_ts/variants/random_search.py`：V2 固定方法/参数目录和带 seed 的后端随机候选 sampler。
- `backend/harnessing_ts/variants/prompts/`：V1-V7 独立 prompt overlay；V0 不应依赖 overlay，保持基础系统行为不变。
- `backend/harnessing_ts/agent/sdk_runner.py`：Claude Code SDK client wrapper，处理消息收发、工具调用/结果合并、SDK session id、interrupt/close 和 SDK 异常自恢复。
- `backend/harnessing_ts/agent/session_factory.py`：主会话和 node 会话的 prompt、allowed tools、MCP server、LLM invocation config 组装。
- `backend/harnessing_ts/mcp/server.py`：MCP tool schema 和 callback 绑定；暴露治理、审计、V2 random sampler 和知识库确定性工具。
- `backend/harnessing_ts/state/workspace_store.py`：workspace 文件/JSON/JSONL repository facade，保留读写状态、日志、运行记录、上传、reset 等外部 API。
- `backend/harnessing_ts/state/workspace_layout.py`：workspace 目录布局、内置 `tools/read_docx.py`、DOCX reference 文本派生。
- `backend/harnessing_ts/runtime_base.py`：项目级 PyTorch 与 workspace 默认依赖基础环境、硬件探测、uv backend 选择、验证和共享 cache metadata。
- `backend/harnessing_ts/server_setup.py`：新服务器聚合初始化，统一执行前端依赖/构建和共享 runtime base 准备。
- `backend/harnessing_ts/knowledge_graph.py`：文件型知识库表、确定性工具、graph view/search/cards、builder/reasoner 调用逻辑。
- `backend/harnessing_ts/knowledge_prompts.py`：Knowledge Builder / Reasoning Agent prompt 文本与知识图谱构建请求文本。
- `backend/harnessing_ts/chain_summary.py`：独立 chain builder agent，读取 runtime workspace 的 logs/reports/runs/tools/user 工件，输出结构化思维链总结和 metric series。
- `backend/harnessing_ts/reference_feature_extractor.py`：独立 Reference Feature Builder、确定性 Python AST 校验、reference evidence 校验、重复执行一致性测试、受控执行和源码/规则检查接口。
- `backend/harnessing_ts/config/`：Markdown prompt、node spec、guidance、native-tools 配置，Python 只读取、解析和校验。
- `frontend/src/main.ts`：当前仍是主要 UI 渲染和事件绑定入口。
- `frontend/src/api.ts`：前端 JSON/Form API client 和错误消息规范。
- `frontend/src/types.ts`：前端共享 DTO / bootstrap 类型。

新增功能时优先落在上述已有边界内。不要把 node 路由规则重新写回 `orchestrator.py`，不要把 workspace layout 细节写回 `WorkspaceStore` 主体，不要把 API 聚合 payload 直接散落在路由函数里。

## Git 管理

所有关键修改必须通过 git 妥善管理：

- **每次完成一个逻辑完整的改动后立即提交**，不要积攒大量未提交的修改。
- **任何 commit 前必须检查并同步 `README.md` 和 `AGENT.md`**。行为、命令、配置、节点协议、运行产物、UI 操作或维护流程发生变化时，两份入口文档必须随代码一起更新；无文档变更时必须在 commit message 写明 `no doc change required: ...`。
- 提交信息（commit message）使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式，清晰描述改动范围和内容。例如：
  - `feat(frontend): incremental live rendering to preserve scroll positions`
  - `fix(backend): correct loopDecision validation for iterative-solving`
  - `docs(architecture): add MCP boundary design notes`
- 提交前确保完整验证通过：
  - 后端：`uv run python -m compileall backend/harnessing_ts`
  - 测试：`uv run pytest -q`
  - 前端：`cd frontend && bun run build`
- `tests/conftest.py` 会自动设置 `TS_HARNESS_SKIP_WORKSPACE_UV=true`，禁止普通单元测试为每个 `tmp_path` 构建完整 `.venv`；runtime-base 必须使用 mock/fake subprocess 做单元测试。
- **禁止提交**：API key、密码、token、`.env` 文件、运行时产物（见下方禁止提交清单）。
- 修改前先 `git status` 确认当前分支和已有改动，避免意外覆盖他人工作。
- 不要提交调试用的临时日志打印、注释掉的代码块、或仅用于本地测试的临时文件。

## 当前 Node Chain（V0 基线）

```text
problem-contract
→ iterative-solving
→ final-summary
```

- `problem-contract`：用用户输入和 `references/**` 拉取/处理数据、exploration、明确真实任务，产出 `user/problem-contract.md`、`user/data-spec.md`，并为独立 Literature Knowledge Builder 写 `knowledge_base/domain-brief.md`。
- `iterative-solving`：可重复执行。每轮先用 `mcp__ts_harness__get_runtime_settings` 读取 `iterativeCandidateCount` 作为 k，提出 k 个候选，用 `Task` subagent 分别做可行性测试和 case review，统一综合后把本轮保留或执行的方法落盘为 `tools/<tool-name>/`，更新 `tools/registry.json` / `user/toolset-spec.md` / `user/solution-plan.md`，执行并把结果写入 `runs/iterations/<iteration-id>/`，最后**先写** `reports/iterations/<iteration-id>-case-review.md`、**再写** `reports/iterations/<iteration-id>-summary.md`、更新 `user/iteration-state.md`。通过 `mcp__ts_harness__finish_node(loopDecision=continue|exit, nextNode=iterative-solving|final-summary, outputPaths=…)` 交还控制权。
- Reference Feature Extractor 构建独立于 node chain。builder 只能依据 task contract、data spec 和 `references/**` 生成 `tools/reference-feature-extractor/`。后端完成 AST 禁用项、reference 原文引用、I/O contract 和重复执行一致性校验后才注入 inspection/extraction MCP。Case review 在工具可用时必须对每个分析 case 和对照 case 调用它，不能用 LLM 目测替代。
- `final-summary`：迭代结束才进。基于 timeline、runs、tools、problem-contract、data-spec 总结整个优化历程、最终工具使用方案、最终结果和系统边界，产出 `reports/final-summary.md` 和 `user/final-solution.md`。如果进入后发现 `user/iteration-state.md` 的 `recommend_exit` 或 contract 指向继续迭代，应标记失败并要求回到 `iterative-solving`。

每个 node 都是独立 Claude Code SDK session，拥有自己的 system prompt、native-tools 白名单和 node 日志。所有节点流转（`enter_node` / `finish_node`）一律走 MCP `mcp__ts_harness__*` 工具，禁止用 JSON 文本块或 `harnessControl.action=…` 等替代控制协议。

消融变体必须保持以下硬差异：

- V1：不创建 node session；main runner 直接获得 Read/Write/Edit/Bash/Web 工具，不提供 node-control、knowledge 或 Task。
- V2：必须调用后端 `mcp__ts_harness__sample_random_candidates` 获取 seed 和恰好 k 个候选；LLM 不得替换或额外重采样。
- V3：不注入 knowledge MCP，禁止 builder 和知识 API 内容，并通过 overlay 禁止读取 reference-derived knowledge。
- V4：从 iterative-solving 的实际 allowed-tools 中移除 `Task`，相同 k 顺序执行。
- V5：后端不要求 case-review outputPath，prompt 禁止 bad/good-case、统计归因和 case visualization。
- V6：后端拒绝 `loopDecision=continue` 以及任何第二次 iterative-solving entry；第一轮仍保留 V0 的完整执行要求。
- V7：禁用独立 Reference Feature Builder，并从 main/node 的实际 MCP allowed-tools 中移除 inspection/extraction 工具。

所有 agent 工具调用都必须在参数中包含 `intend` 字段，用一句简短的话说明本次调用的直接意图。Harness MCP 工具 schema 会强制要求该字段；Claude Code 内置工具也必须按 shared role prompt 的要求尽量携带该字段。后端日志会把同一 `toolUseId` 的工具调用和工具结果合并成一条 `tool_call` 消息；前端默认折叠展示，主标题显示 `intend`，展开后显示详细参数和返回结果。

## 运行记录

流程记录写入：

```text
state/workspace.json
state/nodes/<node-session-id>.json
logs/main.jsonl
logs/nodes/<node-session-id>.jsonl
logs/timeline.jsonl
logs/chain-builder.jsonl
logs/reference-feature-builder.jsonl
runs/registry.jsonl
artifacts/chain-summary.json
state/chain-summary-build.json
state/reference-feature-build.json
```

这些目录是运行产物，默认在 `.gitignore` 中。

前端 `Reset Chat` 重置聊天记录和 agent 工作流记忆，但保留 `data/raw/`、`references/`、`knowledge_base/`、知识图谱以及已验证的 `tools/reference-feature-extractor/`、对应构建状态与 builder 日志。`Reset Workspace` 才清除这些 reference 派生产物；独立 LLM 配置继续保留。

## 禁止提交

- `node_modules/`
- `dist/`
- `.venv/`
- `state/`
- `logs/`
- `user/`
- `data/raw/`
- `data/processed/`
- `references/`
- `artifacts/`
- `plots/`
- `tools/`
- `runs/`
- `reports/`
- `.env*`
- `.secrets/`
- `config.yaml`
