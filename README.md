# HarnessingTS

Time-series tool-use harness built around Python Claude Code SDK sessions.

The harness is designed to help an agent solve time-series analysis tasks by combining:

- background knowledge and references
- data acquisition, conversion, and exploration
- an explicit problem contract
- iterative tool construction, execution, analysis, and case review
- final process and result summaries

It is not a research agent and does not center on method comparison or model leaderboard optimization.

## Node Chain

```text
problem-contract
→ iterative-solving
→ final-summary
```

## Node Responsibilities And Native Tools

The main session is an orchestrator. It should stay read-only and use `Read`, `LS`, `Glob`, and `Grep` to inspect workspace state before requesting a node transition through `harnessControl`. Node sessions receive native tool sets based on their responsibility. MCP governance tools may be attached on official Claude runtimes, but third-party `baseUrl` providers use the text `harnessControl` protocol instead.

Prompt and node configuration text is stored as Markdown, not hard-coded in Python:

```text
backend/harnessing_ts/config/prompts/shared/
backend/harnessing_ts/config/prompts/main/
backend/harnessing_ts/config/prompts/node/
backend/harnessing_ts/config/nodes/<node-type>/spec.md
backend/harnessing_ts/config/nodes/<node-type>/guidance.md
backend/harnessing_ts/config/nodes/<node-type>/native-tools.md
```

Python code reads these files read-only and only handles parsing, validation, and prompt assembly.

| Node | Responsibility | Produces | Native tools |
|---|---|---|---|
| `problem-contract` | Use the user request and references to acquire/process data, explore it, clarify the real task, and write the workflow contract. | `user/problem-contract.md`, `user/data-spec.md` | `Read`, `LS`, `Glob`, `Grep`, `WebFetch`, `WebSearch`, `Write`, `Edit`, `Bash` |
| `iterative-solving` | Each round tries exactly one new method, or one explicit combination of previously persisted tools. The method must first be standardized under `tools/`, then executed and reviewed through data-first case analysis with numeric bad-case attribution. | `tools/**`, `runs/iterations/<iteration-id>/**`, `reports/iterations/<iteration-id>-summary.md`, `user/iteration-state.md` | `Read`, `LS`, `Glob`, `Grep`, `WebFetch`, `WebSearch`, `Write`, `Edit`, `Bash` |
| `final-summary` | If iteration is complete, summarize the full optimization trajectory, final tool-use solution, final results, limitations, and evidence. | `reports/final-summary.md`, `user/final-solution.md` | `Read`, `LS`, `Glob`, `Grep`, `Write`, `Edit` |

Iteration routing:

- `iterative-solving` writes `user/iteration-state.md`.
- If it contains `recommend_exit: false` or `recommend_exit=false`, the backend enters `iterative-solving` again for another round.
- If it contains `recommend_exit: true` or omits a continue marker, the backend advances to `final-summary`.

Global native-tool constraints:

- `Task`, `TodoWrite`, notebook tools, worktree tools, cron tools, and broad automation tools are disallowed by default.
- `Write` and `Edit` are for expected artifact paths. Nodes must not modify `data/raw/**` unless the contract explicitly authorizes a derived copy operation.
- Nodes should not read `backend/**`, `frontend/**`, `state/**`, or `_reference_project/**`. `final-summary` may read `logs/timeline.jsonl` because it is an explicit required input.

## Commands

Install dependencies before running real Claude Code SDK sessions:

```bash
uv sync
```

Check Python code:

```bash
uv run python -m compileall backend/harnessing_ts
```

Start the web UI:

```bash
uv run ts-harness-server
```

Then open:

```text
http://127.0.0.1:4327
```

For UI testing without calling the model:

```bash
TS_HARNESS_DRY_RUN=true uv run ts-harness-server
```

Enable debug actions in the UI, including clearing the current chat log:

```bash
TS_HARNESS_DEBUG=true uv run ts-harness-server
```

Claude Code SDK turn budget defaults to `80`. Override it if a node still hits `error_max_turns`:

```bash
TS_HARNESS_MAX_TURNS=120 uv run ts-harness-server
```

By default, runtime workspaces are separated from this source repository:

```text
~/.harnessingts/workspaces/default
```

Set a different workspace explicitly when needed:

```bash
TS_HARNESS_WORKSPACE=/path/to/time-series-workspace uv run ts-harness-server
uv run ts-harness --workspace /path/to/time-series-workspace init
```

When a runtime workspace is initialized, HarnessingTS automatically makes that folder an isolated `uv` Python project:

```text
/path/to/time-series-workspace/
  pyproject.toml
  uv.lock
  .python-version
  .venv/
  state/runtime.json
```

This workspace environment is separate from the `uv` environment used to run the HarnessingTS backend. Claude Code SDK sessions run with `cwd` set to the runtime workspace, and the prompts require agents to execute Python and shell work through the workspace project:

```bash
uv run python script.py
uv add package-name
uv run --with package-name python script.py
```

Do not install task dependencies into the HarnessingTS source repository environment. Use `TS_HARNESS_SKIP_WORKSPACE_UV=true` only when you intentionally want to skip automatic workspace environment setup.

The browser UI uses this split:

- Left rail: process audit panel. It shows workspace status, node activation state, the node chain, selected-node artifacts, node sessions, node logs, and the timeline.
- Center: main orchestrator chat. The transcript selector above the chat can show all sessions, only the main session, or one specific node session.
- Center toolbar: `Interrupt` stops the currently running main turn or active node. If a node is interrupted, the harness exits that node session and unlocks the main chat so you can add new instructions.
- Right rail: current workspace file tree. This is where node artifacts, data files, generated tools, run outputs, logs, and state files appear.
- Right rail upload: use `Reference Files` to upload PDFs, markdown, text, CSV, or other reference files into `references/`. The upload is recorded in `logs/timeline.jsonl`.

The frontend stays static after each action. Use the refresh button to pull the latest JSONL-backed logs from the backend. Tool calls and tool results are summarized by default; expand each row to inspect the full payload.

There are no human-confirmation gates in the default pipeline. Once a node finishes successfully, the harness automatically advances to the next node. Use `Interrupt` when you need to stop the current run and add new guidance.
- DOCX references are automatically extracted to `<filename>.docx.txt`. Agents can also run `uv run python tools/read_docx.py references/<file>.docx artifacts/<file>.txt`.

Some Anthropic-compatible providers can close the Claude Code control channel when Python in-process MCP tools are attached. For provider smoke tests that only need model I/O, disable harness MCP tools:

```bash
TS_HARNESS_DISABLE_MCP=true uv run ts-harness send "请只回复：调用成功。"
```

For manual `baseUrl` providers, HarnessingTS defaults to a text control protocol instead of in-process MCP. The main agent can autonomously request node transitions by appending:

```json
{"harnessControl":{"action":"enter_node","nodeType":"problem-contract","rationale":"...","inputSummary":"..."}}
```

Node agents return control with:

```json
{"harnessControl":{"action":"finish_node","success":true,"summary":"...","goalMet":false,"outputPaths":["user/problem-contract.md","user/data-spec.md"]}}
```

The frontend hides these control blocks and the backend records the actual transition in `logs/timeline.jsonl`.
After a successful `finish_node`, the backend immediately enters the configured next node. If a node omits `finish_node`, the harness marks that node failed and stops the pipeline instead of waiting for a human gate.

## LLM Configuration

By default the harness uses Claude Code SDK's local login state. If the SDK prints `not login`, either run Claude Code login in your terminal, or configure a manual Anthropic-compatible API endpoint.

Create a local `config.llm.json` from the example:

```bash
cp config.llm.example.json config.llm.json
```

`config.llm.json` may live in the workspace, the shell working directory, or this project root. Environment variables still take precedence.

For DashScope's Anthropic-compatible API, use:

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

`config.llm.json` is ignored by git.

You can also configure it with environment variables:

```bash
export TS_HARNESS_LLM_AUTH_MODE=manual
export TS_HARNESS_LLM_PROTOCOL=anthropic
export TS_HARNESS_LLM_MODEL=qwen3.6-plus
export TS_HARNESS_LLM_BASE_URL=https://dashscope.aliyuncs.com/api/v2/apps/anthropic
export TS_HARNESS_LLM_API_KEY=YOUR_API_KEY
```

Inspect the effective SDK config without printing the full API key:

```bash
uv run ts-harness llm-config
```

Initialize workspace layout and state:

```bash
uv run ts-harness init
```

Send a main-session message:

```bash
uv run ts-harness send "请基于 ECG5000 设计异常样本分类的工具使用流程"
```

Dry-run state transitions without calling Claude Code SDK:

```bash
uv run ts-harness --dry-run init
uv run ts-harness --dry-run start-node problem-contract --input-summary "ECG5000 abnormal sample classification"
uv run ts-harness --dry-run finish-node --summary "Wrote user/problem-contract.md and user/data-spec.md" --goal-met true --output-path user/problem-contract.md --output-path user/data-spec.md
```

## Agent Lightning Training

Training and prompt-optimization support is optional. Install it only when you need rollout/reward loops:

```bash
uv sync --extra training
```

Create a starter Agent Lightning rollout scaffold:

```bash
uv run ts-harness training-template
```

## Project Layout

```text
backend/harnessing_ts/      Python backend, CLI, Claude Code SDK runner, MCP tools
frontend/                  Static browser UI served by FastAPI
examples/training/         Agent Lightning rollout/training scaffold
docs/                      Design notes and architecture docs
_reference_project/        Upstream reference project used for comparison only
```

## Runtime Records

The harness records process state inside the active runtime workspace, not inside the source repository unless you explicitly set `TS_HARNESS_WORKSPACE` to the repository path.

```text
~/.harnessingts/workspaces/default/
  pyproject.toml
  uv.lock
  .python-version
  .venv/
  user/
  data/
  references/
  artifacts/
  plots/
  tools/
  runs/
  reports/
  state/workspace.json
  state/runtime.json
  state/nodes/<node-session-id>.json
  logs/main.jsonl
  logs/nodes/<node-session-id>.jsonl
  logs/timeline.jsonl
```

The most important records are:

```text
state/workspace.json
state/nodes/<node-session-id>.json
logs/main.jsonl
logs/nodes/<node-session-id>.jsonl
logs/timeline.jsonl
runs/registry.jsonl
```

These files are intentionally frontend-neutral so a later UI can render the same process timeline.
