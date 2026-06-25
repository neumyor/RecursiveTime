# HarnessingTS

Time-series tool-use harness built around Python Claude Code SDK sessions.

The harness is designed to help an agent solve time-series analysis tasks by combining:

- background knowledge and references
- data acquisition, conversion, and exploration
- an explicit problem contract
- iterative tool construction, execution, analysis, and case review
- final process and result summaries

It is not a research agent and does not center on method comparison or model leaderboard optimization.

## Quick Start

### 1. Install prerequisites

HarnessingTS requires Python 3.11+, Git, [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh/), and the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/getting-started). The Python Claude Code SDK starts the CLI as a subprocess, so installing only the Python dependencies is not sufficient. Anthropic's generic documentation shows npm; this project standardizes on Bun's compatible global package installation.

Run these commands in order on a new machine:

```bash
# Install uv and Bun if they are not already available.
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://bun.sh/install | bash

# Make Bun and Bun-installed global commands visible in this shell.
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

# Claude Code must be installed after Bun is available.
bun install --global @anthropic-ai/claude-code

# Verify all required executables before continuing.
uv --version
bun --version
claude --version
claude doctor
```

Persist the following lines in `~/.zshrc`, `~/.bashrc`, or the service account's shell profile; otherwise `claude` may disappear from `PATH` after opening a new terminal:

```bash
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
```

### 2. Clone and prepare HarnessingTS

```bash
git clone https://github.com/neumyor/RecursiveTime.git
cd RecursiveTime

# Install the backend and build the frontend/runtime base.
uv sync
uv run ts-harness setup-server
```

`setup-server` runs the frozen frontend Bun install, builds `frontend/dist`, detects the available accelerator, and prepares the shared PyTorch/workspace runtime base. It does **not** install the global Claude Code CLI, which is why the preceding Bun installation step is mandatory.

### 3. Configure Claude Code and environment variables

Choose exactly one authentication mode.

Option A — use Claude Code's own login state:

```bash
# Start Claude Code once and complete its interactive login.
claude

export TS_HARNESS_LLM_AUTH_MODE=sdk-default
```

Option B — use an Anthropic-compatible API endpoint:

```bash
export TS_HARNESS_LLM_AUTH_MODE=manual
export TS_HARNESS_LLM_PROTOCOL=anthropic
export TS_HARNESS_LLM_MODEL=qwen3.6-plus
export TS_HARNESS_LLM_BASE_URL=https://dashscope.aliyuncs.com/api/v2/apps/anthropic
export TS_HARNESS_LLM_API_KEY=YOUR_API_KEY
export TS_HARNESS_LLM_CONTEXT_WINDOW=200k
```

Then set the runtime environment. Use a dedicated workspace for each experiment or ablation variant:

```bash
export TS_HARNESS_WORKSPACE="$HOME/.harnessingts/workspaces/default"
export TS_HARNESS_VARIANT=V0
export TS_HARNESS_CONTROL_MODE=auto
export HOST=127.0.0.1
export PORT=4327

# Confirm the effective model configuration without exposing the full API key.
uv run ts-harness llm-config
```

These variables must be exported in the same shell that starts the server, or configured in its service manager. `TS_HARNESS_LLM_*` values override `config.llm.json`; workspace UI settings provide another persistent configuration path.

### 4. Start and use the application

```bash
uv run ts-harness-server
```

Open [http://127.0.0.1:4327](http://127.0.0.1:4327), then use the UI in this order:

1. Open **Settings** and verify the Main LLM. Configure an independent Knowledge Graph credential only when it should differ from the Main LLM.
2. Upload domain documents with **Reference Files** and task data with **Raw Data Zip**.
3. Send the task definition in the main conversation. The orchestrator enters `problem-contract`, then iterates through solving and case review.
4. Build **Knowledge Graph** after references are available. The builder prioritizes task-relevant diagnostic and judgment metrics, including thresholds, units, measurement methods, channel/lead context, applicability conditions, and uncertainty notes, so `knowledge-to-tools` can query concrete reference rules instead of only broad domain summaries.
5. Run the **knowledge-to-tools** node (or, in `auto` mode, let the orchestrator enter it) after `user/problem-contract.md` and `user/data-spec.md` exist. The node session writes the evidence map, feature plan, deterministic Python module extractor, manifest/README usage contract, real-sample test cases, and evaluation report under `tools/reference-feature-extractor/`, then calls `validate_reference_feature_extractor` to have the backend validate the tool. Synthetic test cases may supplement this but cannot replace the real-sample validation and control/reference evaluation cases.
6. Review node traces, case-review artifacts, tool outputs, and the final summary in the UI and workspace file tree.

### 5. Common development commands

Run commands from the repository root unless the command explicitly changes directory:

```bash
# Backend tests and static compilation.
uv run python -m compileall -q backend/harnessing_ts
uv run pytest -q

# Production frontend build.
cd frontend
bun install --frozen-lockfile
bun run build
cd ..

# Optional hot-reload frontend; keep ts-harness-server running separately.
cd frontend
bun run dev
```

The Vite development UI is available at `http://127.0.0.1:5173`. The production server automatically serves `frontend/dist/` when it exists.

### Environment variable reference

Set variables before `uv run ts-harness-server`. Shell exports apply only to that shell unless added to a profile or service definition.

| Variable | Typical/default value | Purpose |
|---|---|---|
| `BUN_INSTALL` | `$HOME/.bun` | Bun installation directory. |
| `PATH` | include `$BUN_INSTALL/bin` | Makes `bun` and the Bun-installed `claude` executable available. |
| `TS_HARNESS_LLM_AUTH_MODE` | `sdk-default` or `manual` | Selects Claude Code login state or explicit API credentials. |
| `TS_HARNESS_LLM_PROTOCOL` | `anthropic` | Manual endpoint protocol; also supports `openai-compat`. |
| `TS_HARNESS_LLM_MODEL` | provider model name | Main model and default inherited builder model. |
| `TS_HARNESS_LLM_BASE_URL` | provider endpoint | Manual API base URL. |
| `TS_HARNESS_LLM_API_KEY` | secret | Manual API credential; never commit it. |
| `TS_HARNESS_LLM_CONTEXT_WINDOW` | `200k` or `1m` | Optional context-window mode. |
| `TS_HARNESS_WORKSPACE` | `~/.harnessingts/workspaces/default` | Runtime data, tools, state, logs, and reports. |
| `TS_HARNESS_VARIANT` | `V0` | Startup-only ablation profile. |
| `TS_HARNESS_CONTROL_MODE` | `auto` | `auto` or human-approved `manual` node transitions. |
| `HOST` / `PORT` | `127.0.0.1` / `4327` | Web server bind address and port. |
| `TS_HARNESS_DEBUG` | unset | Enables destructive debug/reset controls when `true`; avoid on shared servers. |
| `TS_HARNESS_DRY_RUN` | unset | Skips live SDK execution when `true`. |
| `TS_HARNESS_MAX_TURNS` | SDK default | Optional SDK turn limit. |
| `TS_HARNESS_TORCH_BACKEND` | auto-detected | Override compute backend only when detection is wrong. |

## Node Chain

```text
problem-contract
→ knowledge-to-tools
→ iterative-solving
→ final-summary
```

`knowledge-to-tools` runs only for variants that opt in (V0-V3, V5, V6). V7 (`No Knowledge-to-Tools Node`) skips it: the chain becomes `problem-contract → iterative-solving → final-summary` and no reference feature extractor is built.

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
  Startup-only V0-V7 profile registry, public capability metadata, node purpose/input/output overrides, and variant prompt routing.

backend/harnessing_ts/variants/random_search.py
  V2 fixed method/parameter catalog and seeded backend candidate sampler.

backend/harnessing_ts/variants/prompts/
  Isolated prompt overlays for V1-V7; V0 continues to use the base prompts unchanged.

backend/harnessing_ts/agent/sdk_runner.py
  Claude Code SDK client wrapper, message translation, tool-call/result merging, interrupt/close behavior, and SDK failure recovery.

backend/harnessing_ts/agent/session_factory.py
  Main/node SDK runner construction: prompts, allowed tools, MCP server wiring, and LLM invocation config.

backend/harnessing_ts/mcp/server.py
  MCP governance, audit, runtime-settings, V2 random-candidate sampling, knowledge-query, and deterministic knowledge-base tool schemas.

backend/harnessing_ts/runtime_base.py
  Machine-local PyTorch and workspace dependency runtime-base preparation, hardware detection, verification, and shared uv-cache metadata.

backend/harnessing_ts/server_setup.py
  Aggregated first-server setup for frontend dependency/build preparation and the shared machine runtime base.

backend/harnessing_ts/state/workspace_store.py
  Workspace repository facade for JSON/JSONL state, logs, file reads, uploads, reset behavior, runtime settings, and run/artifact records.

backend/harnessing_ts/state/workspace_layout.py
  Runtime workspace directory layout, built-in read_docx helper, and DOCX reference text derivatives.

backend/harnessing_ts/knowledge_graph.py
  File-backed knowledge-base tables, deterministic knowledge tools, graph view/search/cards, and builder/reasoner execution.

backend/harnessing_ts/knowledge_prompts.py
  Literature Knowledge Builder and Knowledge Reasoning Agent prompts, including the diagnostic/judgment metric extraction priority used to support `knowledge-to-tools`.

backend/harnessing_ts/chain_summary.py
  Independent chain builder agent for reading runtime logs/reports/runs and producing a structured, frontend-renderable decision-chain summary.

backend/harnessing_ts/reference_feature_extractor.py
  Main-session reference feature extractor validator/executor, reference-evidence checker, and main-session inspection contract. The main session writes the artifacts during the `knowledge-to-tools` node; the backend performs the strong validation pass and runs determinism tests on demand.

frontend/src/main.ts
  Static UI rendering and event binding.

frontend/src/api.ts
  Frontend HTTP helpers and error-message normalization.

frontend/src/types.ts
  Shared frontend DTO types.
```

Keep new behavior inside these boundaries. Routing rules belong in `node_state.py`; ablation definitions, catalogs, and prompt differences belong in `variants/`; SDK session construction belongs in `agent/session_factory.py`; aggregate API response shape belongs in `api/payloads.py`; workspace layout details belong in `state/workspace_layout.py`. Variant behavior must be enforced by capabilities, tool availability, or backend contracts where possible; prompt text alone is not a sufficient guard.

The browser receives main-session, node-session, knowledge-graph-builder, chain-summary-builder, runtime-status, and workspace-file updates through the `/api/events` Server-Sent Events stream. The frontend does not poll `/api/live`: the SSE bootstrap event supplies initial/reconnect state, and keyed DOM reconciliation only inserts, moves, updates, or removes messages whose stable ids changed. `/api/live` is retained for API compatibility and diagnostics only.

The following node table describes the V0 full-system baseline. V1 removes the chain entirely; V2-V7 apply the enforced differences documented under Ablation variants.

| Node | Responsibility | Produces | Native tools |
|---|---|---|---|
| `problem-contract` | Use the user request and references to acquire/process data, explore it, and clarify the real task. It may optionally prepare a domain brief for the independent literature knowledge builder. | `user/problem-contract.md`, `user/data-spec.md` | `Read`, `LS`, `Glob`, `Grep`, `WebFetch`, `WebSearch`, `Write`, `Edit`, `Bash` |
| `knowledge-to-tools` | The main session directly writes the deterministic reference feature extractor (`tools/reference-feature-extractor/**`) using task contract, data spec, `references/**`, the knowledge graph (if available) and its own domain knowledge. It must first write `evidence-map.json` and `feature-plan.json`, then implement an importable Python API plus CLI wrapper, run real-sample and control/reference evaluation, write `evaluation-report.json`, and call `mcp__ts_harness__validate_reference_feature_extractor` so the backend performs the strong validation pass. Once validated, later nodes should use the README/manifest Python API directly for large inputs; MCP inspection/extraction remains a compatibility path. | `tools/reference-feature-extractor/**`, `tools/reference-feature-extractor/evidence-map.json`, `tools/reference-feature-extractor/feature-plan.json`, `tools/reference-feature-extractor/evaluation-report.json`, `state/reference-feature-build.json` | `Read`, `LS`, `Glob`, `Grep`, `WebFetch`, `WebSearch`, `Write`, `Edit`, `Bash` |
| `iterative-solving` | Repeated iteration node. Each round first calls `mcp__ts_harness__get_runtime_settings` to read `iterativeCandidateCount`, proposes k candidates, assigns `Task` subagents to independently test/review candidates, synthesizes the evidence, standardizes retained methods or combinations under `tools/`, executes the selected solution, writes candidate review, case review, iteration summary, and updates iteration state. | `tools/**`, `runs/iterations/<iteration-id>/**`, `reports/iterations/<iteration-id>-candidate-review.md`, `reports/iterations/<iteration-id>-case-review.md`, `reports/iterations/<iteration-id>-summary.md`, `user/iteration-state.md` | `Read`, `LS`, `Glob`, `Grep`, `Task`, `WebFetch`, `WebSearch`, `Write`, `Edit`, `Bash` |
| `final-summary` | If iteration is complete, summarize the full optimization trajectory, final tool-use solution, final results, limitations, and evidence. | `reports/final-summary.md`, `user/final-solution.md` | `Read`, `LS`, `Glob`, `Grep`, `Write`, `Edit` |

Case review and summary have separate roles:

- Candidate review records the k source, candidate hypotheses, subagent results, metrics, bad-case review summaries, relation to knowledge graph findings, and the unified retain/drop/compose decision.
- Case review centers on bad cases. If there are fewer than 10 bad cases, every bad case must be analyzed. If there are many, the node must define a task-appropriate sampling strategy and deeply analyze 5-20 bad cases.
- Every reviewed sample must include a visualization path, raw input evidence, current-method evidence, comparison to a good case/prototype/reference case, and an explicit explanation level.
- When the validated reference feature extractor is available, case review must inspect its contract/source and call it for every analyzed bad case and every comparison case. Visual or LLM-only judgment cannot replace its numeric, reference-backed result.
- All case-review images live under `runs/iterations/<iteration-id>/case-review/visualizations/` and must be generated at 250 DPI. After per-case analysis and statistical synthesis, the node must create one or more sample-inspired summary PNGs named with the `summary_` prefix, using a 16:9 canvas and blue/orange/green/red as the preferred emphasis palette.
- Case review ends with statistical analysis over all bad cases or the largest computable bad-case set.
- Iteration summary should not duplicate per-case analysis. It should describe the tool/method change, execution command, aggregate metrics, target gap, 3-5 high-level case-review findings, and next-node decision.

Iteration routing:

- Node transitions are controlled through MCP, not by parsing markdown artifacts.
- `iterative-solving` must call `mcp__ts_harness__finish_node` with `loopDecision: "continue"` and `nextNode: "iterative-solving"` to run another iteration.
- `iterative-solving` must call `mcp__ts_harness__finish_node` with `loopDecision: "exit"` and `nextNode: "final-summary"` to stop iteration and summarize.
- `user/iteration-state.md` still records `recommend_exit` for auditability. It is not the control source, but the backend validates that it does not contradict the structured MCP `loopDecision`.
- Successful `iterative-solving` completion must include output paths for candidate review, case review, iteration summary, and `user/iteration-state.md`; candidate-only reports are rejected.

Node-protocol recovery:

- The harness treats `mcp__ts_harness__finish_node` as the only valid way to leave a node session. If the SDK call itself crashes (control-request timeout, subprocess error, network drop, etc.) the harness marks the node as `failed` with the SDK error in the summary, releases the active-node lock, and re-raises the original exception to the HTTP caller so the user can see what happened. The next main turn is not blocked.
- If the SDK returns normally but the agent never called `finish_node`, the harness sends a bounded reminder turn inside the same node session asking the agent to inspect the workspace and call `finish_node` (with `success=false` if it cannot proceed). If the reminder turn also ends without `finish_node`, the harness gives up, marks the node as `failed`, and releases the lock so the orchestrator can recover on the next main turn.
- A node that the user already paused or whose `finish_node` call is awaiting human approval is not overwritten by the recovery flow.

Global native-tool constraints:

- `Task` is allowed only where listed in the node native tools. `TodoWrite`, notebook tools, worktree tools, cron tools, and broad automation tools are disallowed by default.
- `Write` and `Edit` are for expected artifact paths. `problem-contract` may create missing raw inputs without overwriting existing files; derived, cleaned, converted, or extracted data belongs under `data/processed/**`. All later nodes treat `data/raw/**` as read-only.
- Nodes should not read `backend/**`, `frontend/**`, `state/**`, or `_reference_project/**`. `final-summary` may read `logs/timeline.jsonl` because it is an explicit required input.
- Ordinary domain knowledge should be queried through `mcp__ts_harness__query_knowledge`; nodes should not read `knowledge_base/tables/*.csv`, `knowledge_base/indexes/**`, or `knowledge_base/cache/**` unless explicitly debugging the knowledge base.
- Nodes must treat server processes as shared infrastructure. Long-running Bash commands should use `timeout` or recorded PID files under the current run directory. Agents must not use broad process killers such as `pkill`, `killall`, `pgrep | kill`, or global `kill -9`; they may terminate only PIDs that are proven to have been started by the same node/subagent in the same workspace, first with normal `kill`, and only escalate to `kill -9` for that exact PID after rechecking ownership.

## Deploy On A Server

HarnessingTS can run on a Linux/macOS server and be opened through the same network, a reverse proxy, or a VPN. Complete the Quick Start prerequisites first, including installing Claude Code globally with Bun and persisting Bun's global binary directory in `PATH` for the service account.

After authentication and LLM variables are configured, use this server-specific sequence:

```bash
git clone https://github.com/neumyor/RecursiveTime.git
cd RecursiveTime
uv sync
uv run ts-harness setup-server

export HOST=0.0.0.0
export PORT=4327
export TS_HARNESS_WORKSPACE=/srv/harnessingts/workspaces/v0
export TS_HARNESS_VARIANT=V0
export TS_HARNESS_CONTROL_MODE=auto

uv run ts-harness-server
```

The server creates and initializes `TS_HARNESS_WORKSPACE` automatically on first start. During startup, the terminal shows initialization progress and prints the Web UI URL only after initialization completes.

Use a different workspace path for each ablation variant. Replace `V0` and `/v0` together, for example with `V3` and `/v3`. To use a manual LLM endpoint, add `TS_HARNESS_LLM_*` variables to the launch environment or configure the workspace from the UI.

The server prints a `LAN access URL` when it can detect the machine's LAN address. From another computer, open:

```text
http://<server-ip-or-hostname>:4327
```

Open the port in the server firewall if needed:

   ```bash
   # Ubuntu ufw
   sudo ufw allow 4327/tcp

   # firewalld
   sudo firewall-cmd --add-port=4327/tcp --permanent
   sudo firewall-cmd --reload
   ```

For long-running use, run the process under a service manager such as `systemd`, `supervisord`, Docker, tmux, or a platform process manager:

   ```ini
   [Unit]
   Description=HarnessingTS
   After=network.target

   [Service]
   User=harness
   WorkingDirectory=/path/to/HarnessingTS
   Environment=BUN_INSTALL=/home/harness/.bun
   Environment=PATH=/home/harness/.bun/bin:/usr/local/bin:/usr/bin:/bin
   Environment=HOST=0.0.0.0
   Environment=PORT=4327
   Environment=TS_HARNESS_WORKSPACE=/srv/harnessingts/workspaces/v0
   Environment=TS_HARNESS_VARIANT=V0
   EnvironmentFile=/etc/harnessingts.env
   ExecStart=/usr/bin/env uv run ts-harness-server
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

Place the selected `TS_HARNESS_LLM_*` variables in `/etc/harnessingts.env` with permissions restricted to the service account. The explicit Bun `PATH` is required so the SDK can find the Bun-installed `claude` executable under a non-interactive service manager.

If the server is reachable from untrusted networks, put it behind authentication, HTTPS, and network allowlisting. Keep `TS_HARNESS_DEBUG` unset in shared or public deployments because debug actions include workspace reset controls.

Optional launch behavior is controlled by `TS_HARNESS_DRY_RUN`, `TS_HARNESS_DEBUG`, and `TS_HARNESS_MAX_TURNS`; see the centralized environment-variable table in Quick Start.

### Ablation variants

Select one immutable experiment profile through `TS_HARNESS_VARIANT` before starting the server. `V0` is the default.

| ID | Profile | Enforced behavior |
|---|---|---|
| `V0` | Full HarnessingTS | Full node chain, knowledge graph, k candidates, independent subagents, candidate/case review, tool standardization, iteration memory, and adaptive stopping. |
| `V1` | Single-Agent Tool Use | One main coding-agent session with read/write/bash access. Node control, knowledge graph, Task subagents, structured case review, and iteration state are unavailable. |
| `V2` | Random Search | The backend-only `mcp__ts_harness__sample_random_candidates` tool generates a seed and exactly k unique configurations from a fixed catalog; the LLM may execute but may not replace them. |
| `V3` | No Knowledge Graph | Removes knowledge tools, builder operations, API graph contents, and reference-derived knowledge from problem framing, candidate generation, and error attribution. |
| `V4` | No Independent Subagents | Removes `Task` from iterative-solving; the same k candidates are implemented and reviewed sequentially by the node agent. |
| `V5` | No Case Review | Removes case-review artifacts, bad/good-case analysis, statistical error attribution, and case visualizations. |
| `V6` | One-Shot Harness | Keeps the full first iteration, but the backend rejects `continue` and any second iterative-solving entry. |
| `V7` | No Knowledge-to-Tools Node | Keeps the full workflow but skips the `knowledge-to-tools` node: no reference feature extractor is built, the chain becomes `problem-contract → iterative-solving → final-summary`, and the `validate_reference_feature_extractor`, `extract_reference_features`, and `inspect_reference_feature_extractor` MCP tools are not exposed. |

The selected profile is parsed once during process startup, recorded in workspace state/timeline, exposed by bootstrap/live APIs, and highlighted in the left-side Workspace card. Invalid values fail fast. Use a separate `TS_HARNESS_WORKSPACE` per experiment to prevent artifacts from different variants from sharing state. V6 uses the current `iterativeCandidateCount`; set that value to the desired one-shot total candidate budget before the iteration begins when matching V0's average total candidate count.

There is intentionally no runtime variant-switch API. Restart the process to select another variant. V4 removes `Task` from the actual SDK allowed-tools list, V5 removes case review from backend `finish_node` output validation, and V6 rejects both iterative `continue` and any second iterative node entry.

Runtime iteration and knowledge extraction settings are stored in workspace state and can be changed from the UI:

- `iterativeCandidateCount`: number of candidates proposed by each `iterative-solving` round, bounded from 1 to 8.
- `knowledgeGraphExtractionDepth`: graph extraction depth used by the knowledge builder, bounded from 1 to 4.

### Runtime workspaces and package indexes

Runtime workspaces are isolated `uv` projects stored outside this source repository by default:

```text
~/.harnessingts/workspaces/default
```

Set a different workspace by changing `TS_HARNESS_WORKSPACE` in the centralized Quick Start environment block before launching the server. The server initializes a missing workspace automatically.

`setup-server` prepares `.runtime-base/`, a machine-local environment and uv cache. It detects the host accelerator, asks uv to select the PyTorch backend, resolves PyTorch plus the full default workspace dependency set, verifies imports and the actual PyTorch device backend, and records exact versions in `.runtime-base/runtime-base.json`. New workspaces pin those verified versions and reuse `.runtime-base/uv-cache`.

Use `prepare-runtime-base` directly only when rebuilding the compute dependency base independently:

```bash
uv run ts-harness prepare-runtime-base
```

Useful environment variables:

```bash
# Override PyTorch backend selection only when automatic detection is wrong.
TS_HARNESS_TORCH_BACKEND=cpu uv run ts-harness setup-server

# Use a faster Python package index for both setup-server and workspace uv sync.
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
UV_INDEX_STRATEGY=unsafe-best-match \
uv run ts-harness setup-server
```

`UV_DEFAULT_INDEX` changes uv's default package index. `UV_INDEX` can add extra indexes. Older `UV_INDEX_URL` and `UV_EXTRA_INDEX_URL` names may still work, but prefer `UV_DEFAULT_INDEX` and `UV_INDEX`. PyTorch CUDA wheels are still resolved through the PyTorch index written into the workspace `pyproject.toml`, unless that wheel source is also mirrored.

## Verification

Use the single verification sequence in **Quick Start → Common development commands** before committing behavior changes. Keeping that sequence in one place prevents backend and frontend checks from drifting apart.

Tests set `TS_HARNESS_SKIP_WORKSPACE_UV=true` automatically through `tests/conftest.py`; unit tests must not create a full `.venv` for every temporary workspace. Runtime-base behavior is covered with mocked uv commands in `tests/test_runtime_base.py`, while V0-V7 capabilities, contracts, prompts, and sampler behavior are covered in `tests/test_ablation_variants.py`.

Runtime workspace layout:

```text
/path/to/time-series-workspace/
  pyproject.toml
  uv.lock
  .python-version
  .venv/
  state/runtime.json
```

This environment is separate from the backend project. SDK sessions run with `cwd` set to the runtime workspace, so Python and shell work should use the workspace project:

```bash
uv run python script.py
uv add package-name
uv run --with package-name python script.py
```

Do not install task dependencies into the HarnessingTS source repository environment. Use `TS_HARNESS_SKIP_WORKSPACE_UV=true` only when intentionally skipping automatic workspace setup.

The browser UI uses this split:

- Left rail: process audit panel. It shows workspace status, node activation state, the node chain, selected-node artifacts, node sessions, node logs, and the timeline.
- Center: main orchestrator chat. The transcript selector above the chat can show all sessions, only the main session, or one specific node session.
- Center toolbar: `Interrupt` pauses the currently running main turn or active node. If a node is paused, you can add guidance and resume it from the composer.
- Center toolbar: `Reset Chat` clears chat logs, node sessions, workflow state, generated tools including `tools/reference-feature-extractor/`, `state/reference-feature-build.json`, reports, runs, and processed data while preserving `data/raw/`, `references/`, and the built knowledge graph. `Reset Workspace` performs the full destructive reset and also removes those preserved reference and knowledge-graph artifacts.
- Settings panels: configure main-session and knowledge-graph LLM settings plus `iterativeCandidateCount` and `knowledgeGraphExtractionDepth`. The reference feature extractor is built by the main session during the `knowledge-to-tools` node and reuses the main LLM, so it has no separate credentials.
- Knowledge workbench: build/pause/continue the independent literature knowledge graph, inspect knowledge/evidence/class/relation cards, and query the graph through natural language.
- Chain summary card: shows iteration and metric counts plus a `features: …` suffix indicating whether the validated reference feature extractor is in place (`ready · N features`, `failed`, or `disabled · <variant>`). The detailed artifacts live under `tools/reference-feature-extractor/` in the workspace file tree.
- Chain summary page: open from the right rail CTA under Knowledge Graph, run the independent chain builder, inspect metric-over-iteration charts, and read the evidence-based decision chain with sample visualizations.
- Right rail: current workspace file tree. This is where node artifacts, data files, generated tools, run outputs, logs, and state files appear. The tree omits infrastructure-heavy directories such as `.git`, `.venv`, `node_modules`, and `__pycache__`; other workspace entries are shown up to 5 levels deep, with each directory capped at 100 displayed children and a visible local truncation warning when a directory exceeds that cap.
- Right rail upload: use `Reference Files` to upload PDFs, markdown, text, CSV, or other reference files into `references/`. The upload is recorded in `logs/timeline.jsonl`.
- Right rail upload: use `Raw Data Zip` to upload a `.zip` archive and extract it into `data/raw/` as original data. The backend rejects unsafe archive paths such as `../...` and records the upload in `logs/timeline.jsonl`.

The frontend stays synchronized through SSE after each action. It incrementally reconciles messages by stable id, so unchanged messages, expanded tool cards, images, and scroll state are preserved instead of rebuilding the transcript. Tool calls and tool results are merged into a single collapsed tool message. The collapsed row primarily shows the call's `intend` field; expand it to inspect detailed parameters and returned results.

Default control mode is `auto`. Once a node finishes successfully, the harness automatically advances to the next node. Set `TS_HARNESS_CONTROL_MODE=manual` when you want every node entry and node completion to require explicit approval in the left-side Pending Control panel.
- DOCX references are automatically extracted to `<filename>.docx.txt`. Agents can also run `uv run python tools/read_docx.py references/<file>.docx artifacts/<file>.txt`.

The backend records all accepted or parked control transitions in `logs/timeline.jsonl`. If a node omits `finish_node`, the harness marks the node failed and stops the pipeline.

When `final-summary` has completed and no node is active, the backend treats the pipeline as complete. Further `enter_node` requests are rejected until the workspace is reset, which prevents delayed SDK tool results from re-entering an already completed node.

## LLM Configuration

Follow Quick Start step 3 for the actual authentication and environment-variable commands. The effective configuration precedence is:

1. `TS_HARNESS_LLM_*` environment variables.
2. `config.llm.json` in the workspace, current directory, or project root.
3. Claude Code's local login state when `authMode` is `sdk-default`.

The web Settings page persists the Main LLM configuration in the active workspace. The Knowledge Graph builder can override it independently; the reference feature extractor is built by the main session during `knowledge-to-tools` and uses the main-session configuration.

`config.llm.example.json` contains an Anthropic-compatible manual configuration:

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
backend/harnessing_ts/variants/  V0-V7 profiles, random catalog, and prompt overlays
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
  state/reference-feature-build.json
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
