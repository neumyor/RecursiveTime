from __future__ import annotations

from dataclasses import dataclass

from harnessing_ts.config.markdown import node_document, read_prompt_text
from harnessing_ts.schema import NODE_SPECS, NodeType, get_node_spec
from harnessing_ts.tools.compose_tools import build_node_native_tools


@dataclass(frozen=True)
class PromptContext:
    workspace_path: str
    locale: str = "zh"


def _role_kernel() -> str:
    return read_prompt_text("shared/role-kernel.md")


def _workspace_static(ctx: PromptContext) -> str:
    return _render_template(read_prompt_text("shared/workspace-static.md"), {
        "workspace_path": ctx.workspace_path,
        "locale": ctx.locale,
    })


def _node_specs_guide() -> str:
    chunks: list[str] = []
    for spec in NODE_SPECS:
        lines = [
            f"## {spec.type}",
            f"Purpose: {spec.purpose}",
            f"Requires: {', '.join(spec.requires)}",
            f"Produces: {', '.join(spec.produces)}",
            f"Next: {spec.next}" if spec.next else "Next: none",
        ]
        chunks.append("\n".join([line for line in lines if line]))
    return "\n\n".join(chunks)


def build_main_system_prompt(ctx: PromptContext) -> str:
    return "\n\n---\n\n".join([
        _role_kernel(),
        _workspace_static(ctx),
        read_prompt_text("main/role.md"),
        read_prompt_text("main/control-protocol.md"),
        "## Node Chain\n" + _node_specs_guide(),
    ])


def build_main_attachment(ctx: PromptContext) -> str:
    return _render_template(read_prompt_text("main/attachment.md"), {
        "workspace_path": ctx.workspace_path,
    })


def build_node_system_prompt(node_type: NodeType, ctx: PromptContext) -> str:
    spec = get_node_spec(node_type)
    return "\n\n---\n\n".join([
        _role_kernel(),
        _workspace_static(ctx),
        "\n".join([
            f"## Active Node: {spec.type}",
            f"Purpose: {spec.purpose}",
            f"Required inputs: {', '.join(spec.requires)}",
            f"Required outputs: {', '.join(spec.produces)}",
            f"Native tools available in this node: {', '.join(build_node_native_tools(node_type))}",
            "",
            read_prompt_text("node/execution-rules.md"),
            "",
            read_prompt_text("node/finish-protocol.md"),
        ]),
        _node_specific_guidance(node_type),
    ])


def build_node_attachment(node_type: NodeType, input_summary: str | None = None) -> str:
    input_summary_block = ""
    if input_summary:
        input_summary_block = "\n".join(["", "## Input Summary", input_summary])
    return _render_template(read_prompt_text("node/attachment.md"), {
        "node_type": node_type,
        "input_summary_block": input_summary_block,
    })


def build_chain_summary_system_prompt() -> str:
    return "\n\n---\n\n".join([
        read_prompt_text("chain-summary/system.md"),
        "## JSON Schema\n\n" + read_prompt_text("chain-summary/schema.md"),
    ])


def build_chain_summary_generate_prompt(*, manifest_json: str, draft_path: str) -> str:
    return _render_template(read_prompt_text("chain-summary/generate.md"), {
        "manifest_json": manifest_json,
        "draft_path": draft_path,
    })


def build_chain_summary_repair_system_prompt() -> str:
    return read_prompt_text("chain-summary/repair-system.md")


def build_chain_summary_repair_prompt(
    *,
    validation_error: str,
    attempt: int,
    max_attempts: int,
    draft_path: str,
) -> str:
    return _render_template(read_prompt_text("chain-summary/repair.md"), {
        "validation_error": validation_error,
        "attempt": str(attempt),
        "max_attempts": str(max_attempts),
        "draft_path": draft_path,
    })


def _node_specific_guidance(node_type: NodeType) -> str:
    return node_document(node_type)["guidance"]


def _render_template(template: str, values: dict[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out
