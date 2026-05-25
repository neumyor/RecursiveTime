# AGENT 操作规范

本项目是一个基于 Claude Code SDK 的时间序列 tool-use harness。它不是 research agent；核心目标是让 agent 更可靠地结合背景知识、数据证据和工具集来完成时间序列问题求解。

## 项目入口

本项目后端使用 Python 实现，依赖由 `uv` 管理。前端是 `frontend/` 下的静态页面，直接由 Python FastAPI 服务托管。

安装依赖：

```bash
uv sync
```

初始化工作区：

```bash
uv run ts-harness init
```

发送主会话消息：

```bash
uv run ts-harness send "请基于 ECG5000 设计异常样本分类的工具使用流程"
```

Dry-run 状态流转：

```bash
uv run ts-harness --dry-run init
uv run ts-harness --dry-run start-node problem-definition --input-summary "ECG5000 abnormal sample classification"
uv run ts-harness --dry-run finish-node --summary "Wrote user/problem.md" --goal-met true --output-path user/problem.md
```

Python 语法检查：

```bash
uv run python -m compileall backend/harnessing_ts
```

启动前端工作台：

```bash
uv run ts-harness-server
```

默认地址：

```text
http://127.0.0.1:4327
```

不调用模型的前端测试模式：

```bash
TS_HARNESS_DRY_RUN=true uv run ts-harness-server
```

启用前端调试按钮，包括清空当前聊天记录：

```bash
TS_HARNESS_DEBUG=true uv run ts-harness-server
```

第三方 Anthropic-compatible provider 的最小链路测试可临时关闭 Python in-process MCP：

```bash
TS_HARNESS_DISABLE_MCP=true uv run ts-harness send "请只回复：调用成功。"
```

手动 `baseUrl` provider 默认使用文本控制协议，不依赖 in-process MCP。main agent 通过 `harnessControl.action=enter_node` 请求进入 node；node agent 通过 `harnessControl.action=finish_node` 交还状态。后端负责解析并写入 timeline。

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

## 当前 Node Chain

```text
problem-definition
→ knowledge-ingestion
→ data-conversion
→ data-understanding
→ task-formalization
→ toolset-construction
→ tool-use-planning
→ tool-guided-solving
→ case-review
→ solution-finalization
→ process-summary
```

## 运行记录

流程记录写入：

```text
state/workspace.json
state/nodes/<node-session-id>.json
logs/main.jsonl
logs/nodes/<node-session-id>.jsonl
logs/timeline.jsonl
runs/registry.jsonl
```

这些目录是运行产物，默认在 `.gitignore` 中。

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
