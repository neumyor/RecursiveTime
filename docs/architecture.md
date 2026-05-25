# Time-Series Tool-Use Harness Architecture

This project adapts the harness idea from `_reference_project/v3`, but changes the goal.

The system is not a research agent. It does not center on comparing methods, finding a best model, or optimizing baselines. It is a Python-backed tool-use harness with a lightweight static frontend that helps an agent solve time-series tasks by combining background knowledge, data evidence, explicit tool construction, iteration records, and final audited summaries.

## Core Principles

- Bind to Claude Code SDK as the execution runtime.
- Keep local files and JSONL logs as the source of truth.
- Treat SDK sessions as short-lived execution carriers.
- Express methodology in Markdown prompts and node specs under `backend/harnessing_ts/config/`.
- Use MCP tools only for structured state transitions and audit events when the provider supports them.
- Make the solution a tool-use process, not a model-selection report.
- Treat training as an implementation detail for tools that require it.

## Node Chain

```text
problem-contract
→ iterative-solving
→ final-summary
```

The main session acts as orchestrator. Each node is an independent Claude Code SDK session with its own prompt, tool whitelist, node log, and completion summary.

## Node Roles

1. `problem-contract`

   Use the user request and references to acquire/process data, explore the data, clarify the actual task, and write both the whole-flow problem contract and the data specification.

2. `iterative-solving`

   Each round tries exactly one new method, or one explicit combination of previously persisted tools. The method must first be standardized under `tools` with an interface and usage docs, then executed and reviewed through data-first case analysis. Bad-case attribution must start from raw input values or tool features, compare against good cases/prototypes, and only then connect to domain knowledge.

3. `final-summary`

   If iteration is complete, summarize the full optimization trajectory, final tool-use solution, final results, limitations, and evidence.

## Iteration Routing

`iterative-solving` writes `user/iteration-state.md`.

- `recommend_exit: false` or `recommend_exit=false` makes the backend enter another `iterative-solving` round.
- `recommend_exit: true` or no explicit continue marker lets the backend advance to `final-summary`.

## Filesystem Truth Source

```text
state/workspace.json
state/nodes/<node-session-id>.json
logs/main.jsonl
logs/nodes/<node-session-id>.jsonl
logs/timeline.jsonl
user/problem-contract.md
user/data-spec.md
user/iteration-state.md
user/final-solution.md
artifacts/
data/processed/
tools/
runs/iterations/
reports/iterations/
reports/final-summary.md
```

The frontend is intentionally thin: it renders the same JSONL logs, node metadata, timeline, and runtime state that the Python backend persists on disk.

## MCP Boundary

The MCP server exposes only governance and audit tools:

- `enter_node`
- `finish_node`
- `record_artifact`
- `record_run`
- `request_user_decision`

Methodology stays in Markdown prompts and node specs. MCP should not decide which ECG feature, classifier, or LLM judgment strategy is appropriate; it only records and mutates system state.

## ECG5000 Example

For ECG5000 abnormal sample classification, the harness should guide the agent toward this kind of flow:

1. Build `user/problem-contract.md` and `user/data-spec.md` by combining the user request, ECG reference material, data acquisition through `sktime`, processed data schema, exploration, success criteria, evidence rules, and leakage risks.
2. Run `iterative-solving` one or more times. Each round builds or revises exactly one tool method, or one explicit combination of existing tools, records results under `runs/iterations/<iteration-id>/`, and writes `reports/iterations/<iteration-id>-summary.md`. Case review must include numeric evidence for bad cases, comparison to good cases/prototypes, domain-linked explanations, and explicit "unexplained" labels when evidence is insufficient.
3. When `user/iteration-state.md` recommends exit, run `final-summary` to summarize the full trajectory and final tool-use solution.
