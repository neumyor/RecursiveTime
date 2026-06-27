# AGENT 维护规范

本文面向维护本仓库的 coding agent。README.md 面向人类使用者，负责安装、启动、UI 使用和常见错误；AGENT.md 负责工程边界、实现约束、验证要求和文档同步规则。修改时不要把两者混成同一份文档。

## 文档职责

- README.md：人类用户文档。应说明 prerequisites、安装、启动命令、LLM 配置、变体选择、UI 使用、部署和排错。避免放入内部代码边界、commit 纪律、实现细节。
- AGENT.md：维护 agent 文档。应说明代码所有权边界、不可破坏的系统契约、变体硬约束、测试/验证要求、禁止提交内容。
- docs/：更长的架构设计说明。README 只链接或摘要用户需要知道的内容；AGENT 只记录维护时必须遵守的规则。

任何影响命令、环境变量、变体、节点协议、运行产物、API payload、UI 操作、MCP 工具、prompt 或维护流程的改动，都必须同时检查 README.md 和 AGENT.md。提交前运行：

```bash
git diff -- README.md AGENT.md docs/
```

## 当前系统事实

HarnessingTS 是基于 Python Claude Code SDK 的时间序列 tool-use harness。前端是 `frontend/` 的静态 UI，由 FastAPI 服务托管。运行时状态存在用户指定的 `TS_HARNESS_WORKSPACE`，不是源码仓库。

标准启动入口：

```bash
uv run ts-harness setup-server
HOST=0.0.0.0 PORT=4327 TS_HARNESS_WORKSPACE=/srv/harnessingts/workspaces/nod-kgr-ktl-crv-sub-ada TS_HARNESS_VARIANT=NOD-KGR-KTL-CRV-SUB-ADA TS_HARNESS_CONTROL_MODE=auto uv run ts-harness-server
```

辅助命令：

```bash
uv run ts-harness variants
uv run ts-harness variants --json
uv run ts-harness llm-config
uv run ts-harness --dry-run init
uv run ts-harness --dry-run start-node problem-contract --input-summary "..."
uv run ts-harness --dry-run finish-node --summary "..." --goal-met true --output-path user/problem-contract.md --output-path user/data-spec.md
```

启动配置错误必须 fail fast，禁止静默回退：

- `PORT` 必须是 1-65535 的整数。
- `TS_HARNESS_CONTROL_MODE` 必须是 `auto` 或 `manual`。
- `TS_HARNESS_VARIANT` 必须是合法且已注册的功能码组合。
- 变体错误应提示 `uv run ts-harness variants` 或打印等价 catalog。

## 代码边界

维护时优先保持现有模块边界：

- `backend/harnessing_ts/server.py`：FastAPI app factory、路由注册、后台任务、静态前端托管、启动配置校验。不要在这里新增业务规则。
- `backend/harnessing_ts/api/payloads.py`：`/api/bootstrap` 和 `/api/live` 聚合 payload。
- `backend/harnessing_ts/orchestrator.py`：应用 facade，协调 workspace store、main/node sessions、knowledge services、runner 生命周期和高层能力禁用。
- `backend/harnessing_ts/node_state.py`：node chain 路由、`finish_node` 结构校验、pipeline completion、variant-aware output path 约束。
- `backend/harnessing_ts/variants/profiles.py`：功能码、兼容别名、canonicalization、profile registry、capabilities、node overrides、variant help/catalog 的单一事实源。
- `backend/harnessing_ts/variants/prompts/`：非默认 profile 的 prompt overlay。完整 profile `NOD-KGR-KTL-CRV-SUB-ADA` 不依赖 overlay。
- `backend/harnessing_ts/tools/compose_tools.py`：main/node allowed tools 和 native tools 的 variant-aware 组装。
- `backend/harnessing_ts/agent/session_factory.py`：Claude Code SDK runner 构造、prompt、MCP server、allowed tools、LLM invocation config。
- `backend/harnessing_ts/mcp/server.py`：MCP schema 和 callback 绑定。只暴露已由当前 variant 允许的 callback。
- `backend/harnessing_ts/state/`：workspace 文件/JSON/JSONL repository 和布局。
- `backend/harnessing_ts/knowledge_graph.py` / `knowledge_prompts.py`：知识图谱构建、检索和 direct reference QA。
- `backend/harnessing_ts/reference_feature_extractor.py`：reference feature extractor 的强校验、执行和 inspection。
- `frontend/src/main.ts`：当前主要 UI 渲染和事件绑定入口。
- `frontend/src/types.ts`：frontend DTO 类型。

新增行为应落在已有边界内。不要把 node 路由规则重新写回 `orchestrator.py`，不要把 workspace layout 细节塞进 `WorkspaceStore` 主体，不要把 API 聚合 payload 散落在路由函数里。消融行为必须通过 capabilities、工具注入和后端契约强制实施，不能只靠 prompt 声明。

## 变体系统

`TS_HARNESS_VARIANT` 只在进程启动时解析。运行时不得新增 variant switch API。旧 `V0`-`V5` 仅作为兼容别名，状态、timeline、API 和 UI 应显示 canonical ID。

功能码：

- `NOD`：HarnessingTS node chain。
- `KGR`：文件型 reference knowledge graph 和 graph-backed `query_knowledge`。
- `RQA`：direct reference QA agent，直接基于 `references/**` 回答；与 `KGR` 互斥。
- `KTL`：`knowledge-to-tools` node 和 validated reference feature extractor。
- `CRV`：case review、bad/good-case attribution、case visualization。
- `SUB`：独立 `Task` subagents。
- `ADA`：adaptive iterative solving 和停止决策。
- `DIR`：普通单 agent baseline；不能与其他 code 组合。

已注册 profile：

- `NOD-KGR-KTL-CRV-SUB-ADA`（旧 `V0`）：完整版本。
- `NOD-RQA-KTL-CRV-SUB-ADA`（旧 `V1`）：无 knowledge graph，保留 direct reference QA、KTL、CRV、SUB、ADA。
- `NOD-RQA-KTL-SUB-ADA`（旧 `V2`）：在 direct reference QA 基础上禁用 CRV。
- `NOD-RQA-CRV-SUB-ADA`（旧 `V3`）：在 direct reference QA 基础上禁用 KTL。
- `NOD-RQA-SUB-ADA`（旧 `V4`）：在 direct reference QA 基础上同时禁用 CRV 和 KTL。
- `DIR`（旧 `V5`）：普通单 agent tool-use baseline。

硬约束：

- “消融”表示禁止使用，不是“不要求使用”。
- 无 `NOD` 的 `DIR` 不得创建/进入 node session，不得暴露 node-control MCP。
- 无 `KGR` 不得构建/读取 knowledge graph；图谱 API payload 应为空或拒绝。
- `RQA` profiles 的 `query_knowledge` 必须走 direct reference QA，不得读取 graph tables。
- 无 `KTL` 不得进入 `knowledge-to-tools`，不得注入 validate/extract/inspect reference feature MCP，不得返回 extractor tool metadata，不得运行 extractor。
- 无 `CRV` 时，`finish_node` 必须拒绝 case-review output path；prompt overlay 也要禁止 case-review、bad/good-case attribution 和 visualization。
- 无 `SUB` 时，iterative-solving native tools 中不得包含 `Task`。

## Node Chain 契约

完整 profile 的 baseline chain：

```text
problem-contract
→ knowledge-to-tools
→ iterative-solving
→ final-summary
```

主要契约：

- 所有 node 流转必须走 MCP `mcp__ts_harness__enter_node` / `mcp__ts_harness__finish_node`，不得用 JSON 文本块或 `harnessControl.action` 替代。
- `knowledge-to-tools` 由当前 node/main SDK session 生成 `tools/reference-feature-extractor/**`，后端只做强校验、deterministic executor 和 evidence 检查。
- `iterative-solving` 成功完成必须包含 candidate review、case review（除非无 `CRV`）、iteration summary 和 `user/iteration-state.md`。
- `loopDecision=continue` 必须路由到 `iterative-solving`；`loopDecision=exit` 必须路由到 `final-summary`。
- `user/iteration-state.md` 的 `recommend_exit` 不是控制源，但不得与 structured MCP `loopDecision` 矛盾。
- `final-summary` 只在迭代结束后进入。

Node prompt 和 native tools 约束：

- `Task` 只在 node native tools 允许处可用。
- 节点应把 `data/raw/**` 视为只读；派生数据写入 `data/processed/**`。
- 节点不应读取 `backend/**`、`frontend/**`、`state/**`、`_reference_project/**`；`final-summary` 可读取 `logs/timeline.jsonl`。
- domain knowledge 应通过 `mcp__ts_harness__query_knowledge` 获取，不应直接读 `knowledge_base/tables/*.csv`、`knowledge_base/indexes/**`、`knowledge_base/cache/**`。
- 长时间 Bash 命令应使用 `timeout` 或当前 run 目录 PID/日志；禁止按名称或全局范围使用 `pkill`、`killall`、`pgrep | kill`、批量杀 Python/uv/训练进程或全局 `kill -9`。

## 前端契约

- 前端不应假设 variant ID 形如 `V\d`。variant 是任意 canonical feature-code string。
- 前端应基于 `variant.capabilities` 禁用或标记功能，不应只解析 ID 字符串。
- Bootstrap/live payload 的稳定聚合位置是 `backend/harnessing_ts/api/payloads.py`。
- `/api/events` SSE 是主同步路径；`/api/live` 保留用于兼容和诊断。
- 变体 pill 中完整 profile 和 ablation profile 的样式由显式 class 控制，不得恢复 `.variant-v0` 之类旧假设。

## 运行记录

运行记录写在 workspace 中：

```text
state/workspace.json
state/nodes/<node-session-id>.json
state/runtime-settings.json
state/knowledge-graph-build.json
state/reference-feature-build.json
state/chain-summary-build.json
logs/main.jsonl
logs/nodes/<node-session-id>.jsonl
logs/timeline.jsonl
logs/knowledge-graph-builder.jsonl
logs/knowledge-reasoning.jsonl
logs/chain-builder.jsonl
runs/registry.jsonl
artifacts/chain-summary.json
```

`knowledge-to-tools` 没有独立 builder 日志；它的 SDK 行为记录在对应 main/node log 中，后端强校验结果记录在 `state/reference-feature-build.json`。

## 验证要求

常规验证：

```bash
uv run python -m compileall -q backend/harnessing_ts
uv run pytest -q

cd frontend
bun install --frozen-lockfile
bun run build
```

当前环境注意事项：

- 项目要求 Python `>=3.11`。
- 如果 `uv run pytest` 调到系统 Python 3.10，应改用正确的 3.11 环境；不要把 `datetime.UTC` 等 3.11 API 报错误判为业务失败。
- `tests/conftest.py` 会设置 `TS_HARNESS_SKIP_WORKSPACE_UV=true`，普通单元测试不得为每个 `tmp_path` 构建完整 workspace `.venv`。
- runtime-base 行为必须用 mock/fake subprocess 做单元测试。

变体相关改动至少验证：

- `uv run ts-harness variants` 和 `uv run ts-harness variants --json`。
- default variant resolves to `NOD-KGR-KTL-CRV-SUB-ADA`。
- legacy aliases `V0`-`V5` resolve to canonical IDs。
- unordered IDs canonicalize, e.g. `RQA-NOD-SUB-ADA` -> `NOD-RQA-SUB-ADA`。
- invalid/unknown/valid-but-unregistered combinations fail with actionable messages。
- no-`KTL` profiles do not expose knowledge-to-tools node, extractor tools, extractor metadata, or extractor execution.
- no-`CRV` profiles reject case-review output paths.
- `DIR` exposes direct tools and no node specs.

## Git 和提交

- 每次完成一个逻辑完整改动后提交，不要积攒大量无关改动。
- 提交前检查 `git status`，不要覆盖用户或其他 agent 的未提交改动。
- 不要 revert 未经请求的用户改动。
- commit message 使用 Conventional Commits。
- 行为、命令、配置、节点协议、运行产物、UI 操作或维护流程变化时，README.md 和 AGENT.md 必须同步。

禁止提交：

```text
node_modules/
dist/
.venv/
state/
logs/
user/
data/raw/
data/processed/
references/
artifacts/
plots/
tools/
runs/
reports/
.env*
.secrets/
config.llm.json
config.yaml
```
