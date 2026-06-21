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

The main session is an orchestrator. Before every main-session user turn, the backend injects an authoritative structured progress snapshot containing the active/latest node, completed nodes, anchor-artifact presence, pipeline completion, and a recommended routing action. The main agent should use that snapshot instead of freely scanning the workspace before requesting a transition through `mcp__ts_harness__enter_node`. Node sessions receive native tool sets based on their responsibility and finish through `mcp__ts_harness__finish_node`.

Node control has exactly two modes:

- `TS_HARNESS_CONTROL_MODE=auto`: governance MCP calls are allowed immediately, and the backend advances the configured pipeline automatically.
- `TS_HARNESS_CONTROL_MODE=manual`: governance MCP calls are parked as `pendingControl` in workspace state. The frontend must approve or reject each node entry or node completion.

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

## Code Architecture

The backend is intentionally split into a thin HTTP entrypoint, an application orchestration facade, domain state-machine logic, and filesystem/SDK adapters:

```text
backend/harnessing_ts/server.py
  FastAPI app factory, route registration, background task wiring, static frontend serving.

backend/harnessing_ts/api/payloads.py
  Stable aggregate payloads for /api/bootstrap and /api/live.

backend/harnessing_ts/orchestrator.py
  Application facade coordinating workspace state, main/node sessions, control requests, knowledge operations, and runner lifecycle.

backend/harnessing_ts/node_state.py
  Node-chain routing, loopDecision/nextNode validation, pipeline-complete guard, variant-aware iterative output requirements, and V6 one-shot enforcement.

backend/harnessing_ts/variants/profiles.py
  Startup-only V0-V6 profile registry, public capability metadata, node purpose/input/output overrides, and variant prompt routing.

backend/harnessing_ts/variants/random_search.py
  V2 fixed method/parameter catalog and seeded backend candidate sampler.

backend/harnessing_ts/variants/prompts/
  Isolated prompt overlays for V1-V6; V0 continues to use the base prompts unchanged.

backend/harnessing_ts/agent/sdk_runner.py
  Claude Code SDK client wrapper, message translation, tool-call/result merging, interrupt/close behavior, and SDK failure recovery.

backend/harnessing_ts/agent/session_factory.py
  Main/node SDK runner construction: prompts, allowed tools, MCP server wiring, and LLM invocation config.

backend/harnessing_ts/mcp/server.py
  MCP governance, audit, runtime-settings, V2 random-candidate sampling, knowledge-query, and deterministic knowledge-base tool schemas.

backend/harnessing_ts/runtime_base.py
  Machine-local torch/numpy/scikit-learn runtime-base preparation, hardware detection, verification, and shared uv-cache metadata.

backend/harnessing_ts/server_setup.py
  Aggregated first-server setup for frontend dependency/build preparation and the shared machine runtime base.

backend/harnessing_ts/state/workspace_store.py
  Workspace repository facade for JSON/JSONL state, logs, file reads, uploads, reset behavior, runtime settings, and run/artifact records.

backend/harnessing_ts/state/workspace_layout.py
  Runtime workspace directory layout, built-in read_docx helper, and DOCX reference text derivatives.

backend/harnessing_ts/knowledge_graph.py
  File-backed knowledge-base tables, deterministic knowledge tools, graph view/search/cards, and builder/reasoner execution.

backend/harnessing_ts/knowledge_prompts.py
  Literature Knowledge Builder and Knowledge Reasoning Agent prompts.

backend/harnessing_ts/chain_summary.py
  Independent chain builder agent for reading runtime logs/reports/runs and producing a structured, frontend-renderable decision-chain summary.

frontend/src/main.ts
  Static UI rendering and event binding.

frontend/src/api.ts
  Frontend HTTP helpers and error-message normalization.

frontend/src/types.ts
  Shared frontend DTO types.
```

Keep new behavior inside these boundaries. Routing rules belong in `node_state.py`; ablation definitions, catalogs, and prompt differences belong in `variants/`; SDK session construction belongs in `agent/session_factory.py`; aggregate API response shape belongs in `api/payloads.py`; workspace layout details belong in `state/workspace_layout.py`. Variant behavior must be enforced by capabilities, tool availability, or backend contracts where possible; prompt text alone is not a sufficient guard.

The browser receives main-session, node-session, knowledge-graph-builder, chain-summary-builder, runtime-status, and workspace-file updates through the `/api/events` Server-Sent Events stream. The frontend does not poll `/api/live`: the SSE bootstrap event supplies initial/reconnect state, and keyed DOM reconciliation only inserts, moves, updates, or removes messages whose stable ids changed. `/api/live` is retained for API compatibility and diagnostics only.

The following node table describes the V0 full-system baseline. V1 removes the chain entirely; V2-V6 apply the enforced differences documented under Ablation variants.

| Node | Responsibility | Produces | Native tools |
|---|---|---|---|
| `problem-contract` | Use the user request and references to acquire/process data, explore it, and clarify the real task. It may optionally prepare a domain brief for the independent literature knowledge builder. | `user/problem-contract.md`, `user/data-spec.md` | `Read`, `LS`, `Glob`, `Grep`, `WebFetch`, `WebSearch`, `Write`, `Edit`, `Bash` |
| `iterative-solving` | Repeated iteration node. Each round first calls `mcp__ts_harness__get_runtime_settings` to read `iterativeCandidateCount`, proposes k candidates, assigns `Task` subagents to independently test/review candidates, synthesizes the evidence, standardizes retained methods or combinations under `tools/`, executes the selected solution, writes candidate review, case review, iteration summary, and updates iteration state. | `tools/**`, `runs/iterations/<iteration-id>/**`, `reports/iterations/<iteration-id>-candidate-review.md`, `reports/iterations/<iteration-id>-case-review.md`, `reports/iterations/<iteration-id>-summary.md`, `user/iteration-state.md` | `Read`, `LS`, `Glob`, `Grep`, `Task`, `WebFetch`, `WebSearch`, `Write`, `Edit`, `Bash` |
| `final-summary` | If iteration is complete, summarize the full optimization trajectory, final tool-use solution, final results, limitations, and evidence. | `reports/final-summary.md`, `user/final-solution.md` | `Read`, `LS`, `Glob`, `Grep`, `Write`, `Edit` |

Case review and summary have separate roles:

- Candidate review records the k source, candidate hypotheses, subagent results, metrics, bad-case review summaries, relation to knowledge graph findings, and the unified retain/drop/compose decision.
- Case review centers on bad cases. If there are fewer than 10 bad cases, every bad case must be analyzed. If there are many, the node must define a task-appropriate sampling strategy and deeply analyze 5-20 bad cases.
- Every reviewed sample must include a visualization path, raw input evidence, current-method evidence, comparison to a good case/prototype/reference case, and an explicit explanation level.
- All case-review images live under `runs/iterations/<iteration-id>/case-review/visualizations/` and must be generated at 250 DPI. After per-case analysis and statistical synthesis, the node must create one or more sample-inspired summary PNGs named with the `summary_` prefix, using a 16:9 canvas and blue/orange/green/red as the preferred emphasis palette.
- Case review ends with statistical analysis over all bad cases or the largest computable bad-case set.
- Iteration summary should not duplicate per-case analysis. It should describe the tool/method change, execution command, aggregate metrics, target gap, 3-5 high-level case-review findings, and next-node decision.

Iteration routing:

- Node transitions are controlled through MCP, not by parsing markdown artifacts.
- `iterative-solving` must call `mcp__ts_harness__finish_node` with `loopDecision: "continue"` and `nextNode: "iterative-solving"` to run another iteration.
- `iterative-solving` must call `mcp__ts_harness__finish_node` with `loopDecision: "exit"` and `nextNode: "final-summary"` to stop iteration and summarize.
- `user/iteration-state.md` still records `recommend_exit` for auditability. It is not the control source, but the backend validates that it does not contradict the structured MCP `loopDecision`.
- Successful `iterative-solving` completion must include output paths for candidate review, case review, iteration summary, and `user/iteration-state.md`; candidate-only reports are rejected.

Global native-tool constraints:

- `Task` is allowed only where listed in the node native tools. `TodoWrite`, notebook tools, worktree tools, cron tools, and broad automation tools are disallowed by default.
- `Write` and `Edit` are for expected artifact paths. `problem-contract` may create missing raw inputs without overwriting existing files; derived, cleaned, converted, or extracted data belongs under `data/processed/**`. All later nodes treat `data/raw/**` as read-only.
- Nodes should not read `backend/**`, `frontend/**`, `state/**`, or `_reference_project/**`. `final-summary` may read `logs/timeline.jsonl` because it is an explicit required input.
- Ordinary domain knowledge should be queried through `mcp__ts_harness__query_knowledge`; nodes should not read `knowledge_base/tables/*.csv`, `knowledge_base/indexes/**`, or `knowledge_base/cache/**` unless explicitly debugging the knowledge base.

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

Frontend development is managed by Bun and Vite. Start the backend first, then run the hot-reload frontend in another terminal:

```bash
cd frontend
bun install
bun run dev
```

Open the Vite dev UI at:

```text
http://127.0.0.1:5173
```

Build the production frontend bundle with:

```bash
cd frontend
bun run build
```

When `frontend/dist/` exists, `ts-harness-server` serves the built frontend automatically.

## Deploy On A Server

HarnessingTS can run on a remote Linux/macOS server and be opened from other computers on the same network, or through a reverse proxy/VPN. Install `git`, `uv`, and Bun first, and make either a Claude Code CLI login or LLM API credentials available to the server account.

The normal first-server setup is three commands. The first command clones the repository, the second performs all repository and machine initialization, and the third starts the selected runtime workspace:

```bash
git clone https://github.com/neumyor/RecursiveTime.git && cd RecursiveTime
```

```bash
uv run ts-harness setup-server
```

```bash
HOST=0.0.0.0 PORT=4327 TS_HARNESS_WORKSPACE=/srv/harnessingts/workspaces/v0 TS_HARNESS_VARIANT=V0 uv run ts-harness-server
```

`uv run` synchronizes the Python backend before invoking `setup-server`. The setup command then runs the frozen Bun install, builds `frontend/dist`, detects the machine accelerator, and prepares the shared torch/numpy/scikit-learn runtime base. The server creates and initializes `TS_HARNESS_WORKSPACE` automatically on first start, so a separate `uv sync`, frontend build, `prepare-runtime-base`, or workspace `init` command is not required.

Use a different workspace path for each ablation variant. Replace `V0` and `/v0` together, for example with `V3` and `/v3`. To use a manual LLM endpoint, add the `TS_HARNESS_LLM_*` variables to the same launch environment or configure the workspace from the UI after startup.

The server will print a `LAN access URL` when it can detect the machine's LAN address. From another computer, open:

```text
http://<server-ip-or-hostname>:4327
```

Open the port in the server firewall if needed. Examples:

   ```bash
   # Ubuntu ufw
   sudo ufw allow 4327/tcp

   # firewalld
   sudo firewall-cmd --add-port=4327/tcp --permanent
   sudo firewall-cmd --reload
   ```

For long-running use, run the process under a service manager such as `systemd`, `supervisord`, Docker, tmux, or a platform process manager. A minimal `systemd` service looks like:

   ```ini
   [Unit]
   Description=HarnessingTS
   After=network.target

   [Service]
   WorkingDirectory=/path/to/HarnessingTS
   Environment=HOST=0.0.0.0
   Environment=PORT=4327
   Environment=TS_HARNESS_WORKSPACE=/srv/harnessingts/workspaces/v0
   Environment=TS_HARNESS_VARIANT=V0
   ExecStart=/usr/bin/env uv run ts-harness-server
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

If the server is reachable from untrusted networks, put it behind a reverse proxy with authentication, HTTPS, and network allowlisting. Do not expose a debug server publicly. Keep `TS_HARNESS_DEBUG` unset in shared or public deployments because debug actions include workspace reset controls.

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

### Ablation variants

Select one immutable experiment profile when starting the server. `V0` is the default, so existing launches retain the full system behavior:

```bash
TS_HARNESS_VARIANT=V3 uv run ts-harness-server
```

| ID | Profile | Enforced behavior |
|---|---|---|
| `V0` | Full HarnessingTS | Full node chain, knowledge graph, k candidates, independent subagents, candidate/case review, tool standardization, iteration memory, and adaptive stopping. |
| `V1` | Single-Agent Tool Use | One main coding-agent session with read/write/bash access. Node control, knowledge graph, Task subagents, structured case review, and iteration state are unavailable. |
| `V2` | Random Search | The backend-only `mcp__ts_harness__sample_random_candidates` tool generates a seed and exactly k unique configurations from a fixed catalog; the LLM may execute but may not replace them. |
| `V3` | No Knowledge Graph | Removes knowledge tools, builder operations, API graph contents, and reference-derived knowledge from problem framing, candidate generation, and error attribution. |
| `V4` | No Independent Subagents | Removes `Task` from iterative-solving; the same k candidates are implemented and reviewed sequentially by the node agent. |
| `V5` | No Case Review | Removes case-review artifacts, bad/good-case analysis, statistical error attribution, and case visualizations. |
| `V6` | One-Shot Harness | Keeps the full first iteration, but the backend rejects `continue` and any second iterative-solving entry. |

The selected profile is parsed once during process startup, recorded in workspace state/timeline, exposed by bootstrap/live APIs, and highlighted in the left-side Workspace card. Invalid values fail fast. Use a separate `TS_HARNESS_WORKSPACE` per experiment to prevent artifacts from different variants from sharing state. V6 uses the current `iterativeCandidateCount`; set that value to the desired one-shot total candidate budget before the iteration begins when matching V0's average total candidate count.

There is intentionally no runtime variant-switch API. Restart the process to select another variant. V4 removes `Task` from the actual SDK allowed-tools list, V5 removes case review from backend `finish_node` output validation, and V6 rejects both iterative `continue` and any second iterative node entry.

Runtime iteration and knowledge extraction settings are stored in workspace state and can be changed from the UI:

- `iterativeCandidateCount`: number of candidates proposed by each `iterative-solving` round, bounded from 1 to 8.
- `knowledgeGraphExtractionDepth`: graph extraction depth used by the knowledge builder, bounded from 1 to 4.

By default, runtime workspaces are separated from this source repository:

```text
~/.harnessingts/workspaces/default
```

Set a different workspace explicitly when needed:

```bash
TS_HARNESS_WORKSPACE=/path/to/time-series-workspace uv run ts-harness-server
uv run ts-harness --workspace /path/to/time-series-workspace init
```

Before creating runtime workspaces on a machine, prepare the project-level runtime base once from the HarnessingTS source root:

```bash
uv run ts-harness prepare-runtime-base
# Equivalent direct script:
uv run python scripts/prepare_runtime_base.py
```

For a fresh server, prefer `uv run ts-harness setup-server`; it includes this runtime-base preparation together with frontend installation and production build. Use `prepare-runtime-base` directly only when rebuilding the compute dependency base independently.

This creates the git-ignored `.runtime-base/` environment and cache. The script detects the host OS, CPU architecture, and available NVIDIA CUDA, AMD ROCm, or Apple MPS acceleration; asks `uv` to select the best supported PyTorch backend; resolves compatible versions of `torch`, `numpy`, and `scikit-learn`; verifies the imports and actual PyTorch device backend; and records the exact result in `.runtime-base/runtime-base.json`. Native `uv` progress is displayed while packages are resolved and installed. Set `TS_HARNESS_TORCH_BACKEND` (for example, `cpu` or `cu128`) only when automatic selection must be overridden.

New workspaces pin the verified versions and reuse `.runtime-base/uv-cache`. Package files are materialized through uv's hard-link or copy-on-write cache modes where the filesystem supports them, avoiding repeated downloads and builds while preserving an independent workspace `.venv`, `uv.lock`, and `uv add` workflow. Re-run the command after changing the host GPU/driver, Python version, or when intentionally upgrading the shared package set. Existing workspace projects are not rewritten automatically.

## Verification

Run backend and frontend verification before committing behavior changes:

```bash
uv run python -m compileall backend/harnessing_ts
uv run pytest -q
cd frontend && bun run build
```

Tests set `TS_HARNESS_SKIP_WORKSPACE_UV=true` automatically through `tests/conftest.py`; unit tests must not create a full `.venv` for every temporary workspace. Runtime-base behavior is covered with mocked uv commands in `tests/test_runtime_base.py`, while V0-V6 capabilities, contracts, prompts, and sampler behavior are covered in `tests/test_ablation_variants.py`.

When a runtime workspace is initialized, HarnessingTS automatically makes that folder an isolated `uv` Python project:

```text
/path/to/time-series-workspace/
  pyproject.toml
  uv.lock
  .python-version
  .venv/
  state/runtime.json
```

This workspace environment is separate from the `uv` environment used to run the HarnessingTS backend. When a prepared runtime base is available, the workspace inherits its verified package versions and shared uv cache rather than downloading or rebuilding them. Claude Code SDK sessions run with `cwd` set to the runtime workspace, and the prompts require agents to execute Python and shell work through the workspace project:

```bash
uv run python script.py
uv add package-name
uv run --with package-name python script.py
```

Do not install task dependencies into the HarnessingTS source repository environment. Use `TS_HARNESS_SKIP_WORKSPACE_UV=true` only when you intentionally want to skip automatic workspace environment setup.

The browser UI uses this split:

- Left rail: process audit panel. It shows workspace status, node activation state, the node chain, selected-node artifacts, node sessions, node logs, and the timeline.
- Center: main orchestrator chat. The transcript selector above the chat can show all sessions, only the main session, or one specific node session.
- Center toolbar: `Interrupt` pauses the currently running main turn or active node. If a node is paused, you can add guidance and resume it from the composer.
- Center toolbar: `Reset Chat` clears chat logs, node sessions, workflow state, generated tools, reports, runs, and processed data while preserving `data/raw/`, `references/`, and the built knowledge graph. `Reset Workspace` performs the full destructive reset and also removes raw data, references, and knowledge graph state.
- Settings panels: configure main-session LLM settings, knowledge-graph LLM settings, `iterativeCandidateCount`, and `knowledgeGraphExtractionDepth`.
- Knowledge workbench: build/pause/continue the independent literature knowledge graph, inspect knowledge/evidence/class/relation cards, and query the graph through natural language.
- Chain summary page: open from the right rail CTA under Knowledge Graph, run the independent chain builder, inspect metric-over-iteration charts, and read the evidence-based decision chain with sample visualizations.
- Right rail: current workspace file tree. This is where node artifacts, data files, generated tools, run outputs, logs, and state files appear.
- Right rail upload: use `Reference Files` to upload PDFs, markdown, text, CSV, or other reference files into `references/`. The upload is recorded in `logs/timeline.jsonl`.
- Right rail upload: use `Raw Data Zip` to upload a `.zip` archive and extract it into `data/raw/` as original data. The backend rejects unsafe archive paths such as `../...` and records the upload in `logs/timeline.jsonl`.

The frontend stays synchronized through SSE after each action. It incrementally reconciles messages by stable id, so unchanged messages, expanded tool cards, images, and scroll state are preserved instead of rebuilding the transcript. Tool calls and tool results are merged into a single collapsed tool message. The collapsed row primarily shows the call's `intend` field; expand it to inspect detailed parameters and returned results.

Default control mode is `auto`. Once a node finishes successfully, the harness automatically advances to the next node. Set `TS_HARNESS_CONTROL_MODE=manual` when you want every node entry and node completion to require explicit approval in the left-side Pending Control panel.
- DOCX references are automatically extracted to `<filename>.docx.txt`. Agents can also run `uv run python tools/read_docx.py references/<file>.docx artifacts/<file>.txt`.

The backend records all accepted or parked control transitions in `logs/timeline.jsonl`. If a node omits `finish_node`, the harness marks the node failed and stops the pipeline.

When `final-summary` has completed and no node is active, the backend treats the pipeline as complete. Further `enter_node` requests are rejected until the workspace is reset, which prevents delayed SDK tool results from re-entering an already completed node.

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
backend/harnessing_ts/           Python backend, CLI, Claude Code SDK runner, MCP tools
backend/harnessing_ts/variants/  V0-V6 profiles, random catalog, and prompt overlays
scripts/prepare_runtime_base.py  Direct project runtime-base preparation entrypoint
frontend/                        Static browser UI served by FastAPI
tests/                           Backend contracts, variant enforcement, and API tests
examples/training/               Agent Lightning rollout/training scaffold
docs/                            Design notes and architecture docs
_reference_project/              Upstream reference project used for comparison only
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
  knowledge_base/
  training/
  state/workspace.json
  state/runtime.json
  state/runtime-settings.json
  state/knowledge-graph-build.json
  state/chain-summary-build.json
  state/knowledge-graph-llm.json
  state/nodes/<node-session-id>.json
  logs/main.jsonl
  logs/nodes/<node-session-id>.jsonl
  logs/timeline.jsonl
  logs/knowledge-graph-builder.jsonl
  logs/knowledge-reasoning.jsonl
  logs/chain-builder.jsonl
  artifacts/chain-summary.json
```

The most important records are:

```text
state/workspace.json
state/runtime-settings.json
state/nodes/<node-session-id>.json
logs/main.jsonl
logs/nodes/<node-session-id>.jsonl
logs/timeline.jsonl
runs/registry.jsonl
artifacts/chain-summary.json
```

These files are intentionally frontend-neutral so a later UI can render the same process timeline.
