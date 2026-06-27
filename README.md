# HarnessingTS

HarnessingTS is a time-series tool-use harness built on the Python Claude Code SDK. It helps an agent work through a time-series task with references, data exploration, a problem contract, iterative tool building, evidence review, and a final summary.

It is not a leaderboard or model-comparison framework. The goal is a structured, auditable problem-solving workflow.

## Quick Start

### 1. Install Prerequisites

You need Python 3.11+, Git, [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh/), and the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/getting-started). The Python SDK starts the Claude Code CLI as a subprocess, so installing only Python dependencies is not enough.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://bun.sh/install | bash

export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

bun install --global @anthropic-ai/claude-code

uv --version
bun --version
claude --version
claude doctor
```

Persist Bun's path in your shell profile so `claude` remains available after opening a new terminal:

```bash
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
```

### 2. Prepare The Project

```bash
git clone https://github.com/neumyor/RecursiveTime.git
cd RecursiveTime

uv sync
uv run ts-harness setup-server
```

`setup-server` builds the production frontend and prepares a shared runtime base for task workspaces. It does not install Claude Code globally; that is why the Bun step above is required.

### 3. Configure The LLM

Choose one authentication mode.

Use Claude Code's local login:

```bash
claude
export TS_HARNESS_LLM_AUTH_MODE=sdk-default
```

Or use an Anthropic-compatible endpoint:

```bash
export TS_HARNESS_LLM_AUTH_MODE=manual
export TS_HARNESS_LLM_PROTOCOL=anthropic
export TS_HARNESS_LLM_MODEL=qwen3.6-plus
export TS_HARNESS_LLM_BASE_URL=https://dashscope.aliyuncs.com/api/v2/apps/anthropic
export TS_HARNESS_LLM_API_KEY=YOUR_API_KEY
export TS_HARNESS_LLM_CONTEXT_WINDOW=200k
```

Check the effective configuration without printing the full API key:

```bash
uv run ts-harness llm-config
```

### 4. Start Locally

Use a separate workspace per experiment or ablation variant.

```bash
export TS_HARNESS_WORKSPACE="$HOME/.harnessingts/workspaces/default"
export TS_HARNESS_VARIANT=NOD-KGR-KTL-CRV-SUB-ADA
export TS_HARNESS_CONTROL_MODE=auto
export HOST=127.0.0.1
export PORT=4327

uv run ts-harness-server
```

Open [http://127.0.0.1:4327](http://127.0.0.1:4327).

Useful launch options:

```bash
# Show registered ablation profiles and legacy aliases.
uv run ts-harness variants

# Run the UI without calling the Claude Code SDK.
TS_HARNESS_DRY_RUN=true uv run ts-harness-server

# Enable debug/reset controls. Do not use this on shared/public servers.
TS_HARNESS_DEBUG=true uv run ts-harness-server
```

## Using The UI

Typical flow:

1. Open **Settings** and confirm the Main LLM configuration.
2. Upload domain documents through **Reference Files**.
3. Upload task data through **Raw Data Zip**.
4. Send the task definition in the main chat.
5. Build the **Knowledge Graph** when using a `KGR` profile.
6. Let the node chain run through `problem-contract`, optional `knowledge-to-tools`, `iterative-solving`, and `final-summary`.
7. Inspect node logs, workspace files, run outputs, case-review artifacts, chain summary, and final summary.

Control modes:

- `TS_HARNESS_CONTROL_MODE=auto`: node transitions are accepted automatically.
- `TS_HARNESS_CONTROL_MODE=manual`: each node entry and completion waits for browser approval.

## Ablation Variants

`TS_HARNESS_VARIANT` is read once at process startup. Restart the server to switch variants, and use a different `TS_HARNESS_WORKSPACE` for each experiment.

Feature codes are order-insensitive. For example, `RQA-NOD-SUB-ADA` is accepted and canonicalized to `NOD-RQA-SUB-ADA`.

```bash
uv run ts-harness variants
```

Feature codes:

| Code | Meaning |
|---|---|
| `NOD` | HarnessingTS node chain. |
| `KGR` | File-backed reference knowledge graph and graph-backed `query_knowledge`. |
| `RQA` | Direct reference QA agent over `references/**`; mutually exclusive with `KGR`. |
| `KTL` | `knowledge-to-tools` node and validated reference feature extractor. |
| `CRV` | Structured case review and case-level attribution. |
| `SUB` | Independent `Task` subagents for candidate testing/review. |
| `ADA` | Adaptive iterative solving and stop decisions. |
| `DIR` | Direct single-agent baseline; cannot be combined with other codes. |

Registered profiles:

| Canonical ID | Legacy alias | Description |
|---|---|---|
| `NOD-KGR-KTL-CRV-SUB-ADA` | `V0` | Full HarnessingTS. |
| `NOD-RQA-KTL-CRV-SUB-ADA` | `V1` | Full node workflow without the knowledge graph; `query_knowledge` answers directly from references. |
| `NOD-RQA-KTL-SUB-ADA` | `V2` | Direct reference QA with case review removed. |
| `NOD-RQA-CRV-SUB-ADA` | `V3` | Direct reference QA with `knowledge-to-tools` and reference feature extractor removed. |
| `NOD-RQA-SUB-ADA` | `V4` | Direct reference QA with both case review and knowledge tools removed. |
| `DIR` | `V5` | Ordinary single-agent tool-use baseline with no node chain or harness MCP tools. |

A removed feature is not merely optional. It is blocked by tool availability and backend checks where applicable. For example, no-`KTL` profiles cannot enter `knowledge-to-tools`, cannot validate or run the reference feature extractor, and do not expose extractor metadata through the API.

## Startup Errors

The server validates startup-only configuration before binding the port.

| Error text | What to do |
|---|---|
| `Invalid PORT` | Set an integer from 1 to 65535, for example `PORT=4327`. |
| `Invalid TS_HARNESS_CONTROL_MODE` | Use `auto` or `manual`. |
| `unknown feature code` | Run `uv run ts-harness variants` and choose a listed code. |
| `DIR cannot be combined` | Use `DIR` alone. |
| `KGR and RQA are mutually exclusive` | Choose either graph-backed knowledge or direct reference QA. |
| `syntactically valid but not a registered ablation profile` | Use one of the registered canonical profiles. |

## Server Deployment

For LAN or server use, bind to a non-loopback address and keep all startup-only values in the same service environment.

```bash
export HOST=0.0.0.0
export PORT=4327
export TS_HARNESS_WORKSPACE=/srv/harnessingts/workspaces/nod-kgr-ktl-crv-sub-ada
export TS_HARNESS_VARIANT=NOD-KGR-KTL-CRV-SUB-ADA
export TS_HARNESS_CONTROL_MODE=auto

uv run ts-harness-server
```

One-line launch example:

```bash
HOST=0.0.0.0 \
PORT=4327 \
TS_HARNESS_WORKSPACE=/srv/harnessingts/workspaces/nod-rqa-sub-ada \
TS_HARNESS_VARIANT=NOD-RQA-SUB-ADA \
TS_HARNESS_CONTROL_MODE=auto \
uv run ts-harness-server
```

The server prints a LAN URL when it can detect one. Open the port in your firewall if needed.

For long-running deployments, use a process manager such as `systemd`, `supervisord`, Docker, or tmux. Example `systemd` fragment:

```ini
[Service]
User=harness
WorkingDirectory=/path/to/HarnessingTS
Environment=BUN_INSTALL=/home/harness/.bun
Environment=PATH=/home/harness/.bun/bin:/usr/local/bin:/usr/bin:/bin
Environment=HOST=0.0.0.0
Environment=PORT=4327
Environment=TS_HARNESS_WORKSPACE=/srv/harnessingts/workspaces/nod-kgr-ktl-crv-sub-ada
Environment=TS_HARNESS_VARIANT=NOD-KGR-KTL-CRV-SUB-ADA
EnvironmentFile=/etc/harnessingts.env
ExecStart=/usr/bin/env uv run ts-harness-server
Restart=on-failure
```

Keep API keys in an environment file with restricted permissions. Put public deployments behind authentication, HTTPS, and network allowlisting.

## Workspaces And Runtime Files

Runtime workspaces are separate from the source repository. By default they live under:

```text
~/.harnessingts/workspaces/default
```

Important workspace directories:

```text
references/                 uploaded reference files
data/raw/                   uploaded raw task data
data/processed/             derived task data
user/                       problem contracts, data specs, final solution
tools/                      generated tools and reference feature extractor
runs/                       iteration run outputs
reports/                    candidate/case/final reports
knowledge_base/             knowledge graph tables and cache
state/                      JSON state
logs/                       JSONL logs
```

SDK sessions run with `cwd` set to the runtime workspace. Task dependencies should be installed into that workspace, not into the HarnessingTS source repository:

```bash
uv run python script.py
uv add package-name
uv run --with package-name python script.py
```

## Development Checks

For local code changes:

```bash
uv run python -m compileall -q backend/harnessing_ts
uv run pytest -q

cd frontend
bun install --frozen-lockfile
bun run build
```

The Vite development UI is available at `http://127.0.0.1:5173`:

```bash
cd frontend
bun run dev
```

## Optional Training Scaffold

Training support is optional and not needed for normal use.

```bash
uv sync --extra training
uv run ts-harness training-template
```
