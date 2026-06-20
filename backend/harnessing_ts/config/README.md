# HarnessingTS Config

This directory stores the harness text configuration that is read by the Agent.
Python code should treat these files as read-only inputs: it may parse, validate, and assemble them, but prompt text, node responsibilities, node guidance, and node native-tool lists should live here.

## Files

### `README.md`

This file. It explains the purpose and ownership boundary of the config directory.

### `__init__.py`

Marks this directory as a Python package so the backend can import config helpers.
It should not contain prompt or node content.

### `markdown.py`

Parser and loader for the Markdown configuration files.
It reads files under `prompts/` and `nodes/`, validates required fields, orders the node chain from `next` pointers, and exposes structured data to the backend.

This file should contain parsing logic only, not model-facing prompt content.

## `prompts/`

Prompt fragments shared by sessions or specific to a runner type.
These files are assembled by `backend/harnessing_ts/prompts/compose.py`.

### `prompts/shared/role-kernel.md`

Common identity and behavioral principles for both the main orchestrator and node runners.
This is model-facing text.

### `prompts/shared/workspace-static.md`

Common workspace rules and static runtime assumptions.
Supports template variables such as `{workspace_path}` and `{locale}`.
This is model-facing text.

### `prompts/main/role.md`

Main orchestrator role definition.
It tells the main session to talk with the user and start node sessions rather than doing node work itself.
This is model-facing text.

### `prompts/main/control-protocol.md`

Main-session MCP governance protocol for requesting `enter_node`.
This is model-facing text.

### `prompts/main/attachment.md`

Initial main-session attachment template.
It describes expected workspace layout and supports `{workspace_path}`.
This is model-facing text.

### `prompts/node/execution-rules.md`

Rules shared by all node runners.
This is model-facing text.

### `prompts/node/finish-protocol.md`

Node-session MCP governance protocol for reporting `finish_node`.
This is model-facing text.

### `prompts/node/attachment.md`

Node startup attachment template.
Supports `{node_type}` and `{input_summary_block}`.
This is model-facing text.

### `prompts/chain-summary/`

Chain builder prompt fragments assembled by `backend/harnessing_ts/prompts/compose.py`:

- `system.md`: builder role, evidence rules, Chinese output requirement, and draft-write protocol.
- `schema.md`: the required chain-summary JSON structure.
- `generate.md`: generation task template with `{manifest_json}` and `{draft_path}`.
- `repair-system.md`: constrained local-repair agent rules.
- `repair.md`: validation-repair template with attempt, path, and error variables.

Generation and repair prompts must be changed in these Markdown files rather than embedded in `chain_summary.py`.

## `nodes/<node-type>/`

Each node has its own directory. A node directory must contain exactly these content files:

```text
spec.md
guidance.md
native-tools.md
```

Current node directories:

```text
nodes/problem-contract/
nodes/iterative-solving/
nodes/final-summary/
```

### `nodes/<node-type>/spec.md`

Structured node contract.
It defines:

- `phase`
- `next`
- `purpose`
- `requires`
- `produces`

This file controls node order and the node contract shown to the model and UI.

### `nodes/<node-type>/guidance.md`

Node-specific execution guidance.
It describes how this node should satisfy its contract.
This is model-facing text.

### `nodes/<node-type>/native-tools.md`

Native Claude Code tools visible to this node before harness MCP/text-control tools are added.
One tool per Markdown list item.

Example:

```text
- Read
- LS
- Glob
- Grep
- Write
- Edit
- Bash
```

This file is used by `backend/harnessing_ts/tools/compose_tools.py`.

## Maintenance Rules

- Put model-facing text in Markdown files, not Python files.
- Keep shared behavior in `prompts/shared/`.
- Keep main-only behavior in `prompts/main/`.
- Keep node-runner common behavior in `prompts/node/`.
- Keep chain builder generation, schema, and repair behavior in `prompts/chain-summary/`.
- Keep node-specific responsibility, guidance, and tool access in that node's own directory.
- When adding a node, create a new `nodes/<node-type>/` directory and connect it through the `next` field in `spec.md`.
- Avoid putting multiple unrelated configuration domains into one Markdown file.
