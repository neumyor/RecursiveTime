# Time-Series Tool-Use Harness Architecture

This project adapts the harness idea from `_reference_project/v3`, but changes the goal.

The system is not a research agent. It does not center on comparing methods, finding a best model, or optimizing baselines. It is a Python-backed tool-use harness with a lightweight static frontend that helps an agent solve time-series tasks by combining background knowledge, data evidence, explicit tool construction, iteration records, and final audited summaries.

## Core Principles

- Bind to Claude Code SDK as the execution runtime.
- Keep local files and JSONL logs as the source of truth.
- Treat SDK sessions as short-lived execution carriers.
- Express methodology in Markdown prompts and node specs under `backend/harnessing_ts/config/`.
- Use MCP tools for all structured node state transitions and audit events.
- Make the solution a tool-use process, not a model-selection report.
- Treat training as an implementation detail for tools that require it.

## Implementation Map

The current implementation keeps runtime orchestration, domain routing rules, filesystem state, SDK wiring, and API response shaping in separate modules:

- `backend/harnessing_ts/server.py`: FastAPI app factory, route registration, background task wiring, and static frontend serving.
- `backend/harnessing_ts/api/payloads.py`: aggregate response construction for `/api/bootstrap` and `/api/live`.
- `backend/harnessing_ts/api/realtime.py`: SSE fan-out for session parts, builder state, runtime state, and workspace file changes. The browser uses the SSE bootstrap snapshot and does not poll `/api/live`.
- `backend/harnessing_ts/orchestrator.py`: application facade that coordinates workspace state, main/node sessions, pending control, knowledge operations, and runner lifecycle.
- `backend/harnessing_ts/node_state.py`: node-chain routing and validation, including `loopDecision`, `nextNode`, pipeline completion, and iterative-solving output requirements.
- `backend/harnessing_ts/agent/sdk_runner.py`: Claude Code SDK wrapper for message send/receive, tool-call/result merging, session id capture, interrupt/close, and client recovery after SDK failures.
- `backend/harnessing_ts/agent/session_factory.py`: SDK runner construction for main and node sessions, including prompt assembly, allowed tools, MCP server wiring, and LLM invocation settings.
- `backend/harnessing_ts/mcp/server.py`: MCP schemas and callback binding for governance, audit, runtime settings, knowledge query, and deterministic knowledge-base tools.
- `backend/harnessing_ts/state/workspace_store.py`: repository facade for workspace JSON/JSONL state, logs, file reads, uploads, resets, runtime settings, and run/artifact records.
- `backend/harnessing_ts/state/workspace_layout.py`: runtime workspace directory layout, built-in `tools/read_docx.py`, and DOCX reference text derivatives.
- `backend/harnessing_ts/knowledge_graph.py`: file-backed knowledge-base tables, deterministic tools, graph view/search/cards, and builder/reasoner execution.
- `backend/harnessing_ts/knowledge_prompts.py`: prompt text for the Literature Knowledge Builder and Knowledge Reasoning Agent.
- `backend/harnessing_ts/chain_summary.py`: independent chain builder agent that reads runtime logs, reports, runs, tools, and user artifacts, then writes structured decision-chain JSON for frontend charts and sample evidence cards.
- `frontend/src/main.ts`: static UI rendering and event binding.
- `frontend/src/api.ts`: frontend HTTP helpers and error-message normalization.
- `frontend/src/types.ts`: shared frontend DTO types.

## Node Chain

```text
problem-contract
→ knowledge-to-tools
→ iterative-solving
→ final-summary
```

The main session acts as orchestrator. Each node is a Claude Code SDK session with its own prompt, tool whitelist, log, and completion summary. The `NOD-KGR-KTL-CRV-SUB-ADA` baseline uses the full four-node chain. Variants can disable specific capabilities; for example profiles without `KTL` skip `knowledge-to-tools`, so their chain becomes `problem-contract → iterative-solving → final-summary`.

## Node Roles

1. `problem-contract`

   Use the user request and references to acquire/process data, explore the data, clarify the actual task, and write both the whole-flow problem contract and the data specification.

2. `knowledge-to-tools`

   Use the problem contract, data specification, references, and the knowledge graph when available to build a deterministic reference feature extractor under `tools/reference-feature-extractor/`. The node must write the evidence map, feature plan, importable extractor, manifest/README contract, real-sample test cases, and evaluation report, then call the backend validator before later nodes can treat the extractor as trusted numeric evidence.

3. `iterative-solving`

   Each round tries exactly one new method, or one explicit combination of previously persisted tools. The method must first be standardized under `tools` with an interface and usage docs, then executed and reviewed through data-first case analysis. The node must write the case review before the iteration summary. Bad-case attribution must start from raw input values or tool features, compare against good cases/prototypes, and only then connect to domain knowledge.

4. `final-summary`

   If iteration is complete, summarize the full optimization trajectory, final tool-use solution, final results, limitations, and evidence.

## Iteration Routing

Node transitions are controlled through MCP, not by parsing markdown artifacts.

- `iterative-solving` still writes `user/iteration-state.md` with `recommend_exit` for auditability.
- To continue, `iterative-solving` must call `mcp__ts_harness__finish_node` with `loopDecision: "continue"` and `nextNode: "iterative-solving"`.
- To exit, `iterative-solving` must call `mcp__ts_harness__finish_node` with `loopDecision: "exit"` and `nextNode: "final-summary"`.
- The backend validates those structured MCP parameters and never uses `user/iteration-state.md` as the control source.

## Filesystem Truth Source

```text
state/workspace.json
state/nodes/<node-session-id>.json
logs/main.jsonl
logs/nodes/<node-session-id>.jsonl
logs/timeline.jsonl
logs/knowledge-graph-builder.jsonl
logs/chain-builder.jsonl
user/problem-contract.md
user/data-spec.md
user/iteration-state.md
user/final-solution.md
state/reference-feature-build.json
artifacts/knowledge-graph.json
artifacts/chain-summary.json
artifacts/
data/processed/
tools/reference-feature-extractor/
tools/
runs/iterations/
reports/iterations/
reports/iterations/<iteration-id>-candidate-review.md
reports/iterations/<iteration-id>-case-review.md
reports/iterations/<iteration-id>-summary.md
reports/final-summary.md
```

The frontend is intentionally thin: it renders the same JSONL logs, node metadata, timeline, and runtime state that the Python backend persists on disk.

## Realtime UI Updates

The backend exposes `/api/events` as a Server-Sent Events stream. `SdkRunner.on_part` publishes deduplicated persisted transcripts for main, node, knowledge-graph-builder, and chain-summary-builder sessions. Upload operations publish the refreshed workspace file tree, and task lifecycle events publish runtime snapshots. The stream's bootstrap event provides initial and reconnect state; the frontend does not poll snapshot endpoints. Messages use keyed DOM reconciliation, and other high-cost panels use content signatures so unchanged UI nodes are retained.

## Chain Summary

The chain summary page is opened from the right rail under the Knowledge Graph entry. Its `Generate` action starts an independent chain builder agent, separate from the main session, node sessions, and knowledge graph builder. The agent reads only runtime workspace logs and artifacts, then writes `artifacts/chain-summary.json` and its trace to `logs/chain-builder.jsonl`.

The JSON output contains metric series over iterations and iteration-level decision-chain cards: proposed methods, test results, sample inspirations, optional visualization paths, next-iteration impact, artifacts, and uncertainty. The frontend renders metric series as charts and sample visualization paths through the workspace file preview endpoint.

## Tool Message Protocol

Every agent tool call should include an `intend` argument: one short sentence describing the immediate reason for the call. Harness MCP tools require this field in their JSON schema and strip it before dispatching to business callbacks. Claude Code built-in tools are governed by the shared role prompt and should also include `intend` whenever the underlying tool schema accepts it.

The backend converts SDK `tool_use` messages into `tool_call` parts. When the matching SDK `tool_result` arrives with the same `toolUseId`, the log entry is updated so the call and result are represented as one message:

```json
{
  "type": "tool_call",
  "name": "Read",
  "intend": "Read the contract to confirm the current task boundary.",
  "input": {"file_path": "user/problem-contract.md", "intend": "..."},
  "status": "completed",
  "resultText": "..."
}
```

The frontend renders `tool_call` messages collapsed by default. The row title shows `intend`; expanded details show tool name, status, full parameters, and returned result text.

## MCP Boundary

The MCP server exposes structured harness tools while leaving methodology in Markdown prompts and node specs:

- `enter_node`
- `finish_node`
- `record_artifact`
- `record_run`
- `get_runtime_settings`
- `query_knowledge` when the active variant allows it; `KGR` profiles use the built knowledge graph, while `RQA` reference-QA profiles answer directly from `references/**`
- reference feature extractor validation/inspection/execution tools when the active variant allows `knowledge-to-tools`

MCP should not decide which ECG feature, classifier, or LLM judgment strategy is appropriate. It records or mutates harness state, exposes runtime settings, and provides deterministic access to already-built knowledge and reference-feature services.

## ECG5000 Example

For ECG5000 abnormal sample classification, the harness should guide the agent toward this kind of flow:

1. Build `user/problem-contract.md` and `user/data-spec.md` by combining the user request, ECG reference material, data acquisition through `sktime`, processed data schema, exploration, success criteria, evidence rules, and leakage risks.
2. Run `knowledge-to-tools` to turn reference evidence into a validated deterministic feature extractor under `tools/reference-feature-extractor/`, including evidence mapping, feature planning, real-sample tests, control/reference evaluation, and backend validation.
3. Run `iterative-solving` one or more times. Each round builds or revises exactly one tool method, or one explicit combination of existing tools, records results under `runs/iterations/<iteration-id>/`, writes `reports/iterations/<iteration-id>-case-review.md` first, then writes `reports/iterations/<iteration-id>-summary.md`. Case review centers on bad cases: analyze every bad case when there are fewer than 10, otherwise sample 5-20 cases with an explicit strategy. Each reviewed sample needs a visualization path, raw input evidence, current-method evidence, good-case/prototype comparison, and explanation level. Case review then summarizes statistical patterns across all bad cases or the largest computable bad-case set. Summary should focus on method changes, tool paths, aggregate metrics, target gaps, high-level case-review findings, and next-round decisions rather than duplicating per-case details.
4. When the `finish_node` MCP call requests `loopDecision: "exit"` and `nextNode: "final-summary"`, run `final-summary` to summarize the full trajectory and final tool-use solution.
