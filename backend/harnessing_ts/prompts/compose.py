from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from harnessing_ts.config.markdown import node_document, read_prompt_text
from harnessing_ts.schema import NODE_SPECS, NodeType, get_node_spec
from harnessing_ts.tools.compose_tools import build_node_native_tools
from harnessing_ts.variants import DEFAULT_VARIANT_ID, AblationVariant, get_variant


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


def _node_specs_guide(variant: AblationVariant) -> str:
    chunks: list[str] = []
    for spec in NODE_SPECS:
        if not variant.node_enabled(spec.type):
            continue
        next_node = variant.node_next(spec.type, spec.next)
        lines = [
            f"## {spec.type}",
            f"Purpose: {variant.node_purpose(spec.type, spec.purpose)}",
            f"Requires: {', '.join(variant.node_requires(spec.type, spec.requires))}",
            f"Produces: {', '.join(variant.node_produces(spec.type, spec.produces))}",
            f"Next: {next_node}" if next_node else "Next: none",
        ]
        chunks.append("\n".join([line for line in lines if line]))
    return "\n\n".join(chunks)


def build_main_system_prompt(ctx: PromptContext, variant: AblationVariant | None = None) -> str:
    variant = variant or get_variant(DEFAULT_VARIANT_ID)
    if not variant.node_chain:
        return "\n\n---\n\n".join([
            _role_kernel(),
            _workspace_static(ctx),
            variant.prompt_overlay("main"),
        ])
    chunks = [
        _role_kernel(),
        _workspace_static(ctx),
        read_prompt_text("main/role.md"),
        read_prompt_text("main/control-protocol.md"),
        "## Node Chain\n" + _node_specs_guide(variant),
    ]
    if variant.id != DEFAULT_VARIANT_ID:
        chunks.append(f"## Active Ablation Variant\n\n{variant.id} · {variant.name}\n\n{variant.description}")
    return "\n\n---\n\n".join(chunks)


def build_main_attachment(
    ctx: PromptContext,
    progress: dict[str, Any] | None = None,
    variant: AblationVariant | None = None,
) -> str:
    variant = variant or get_variant(DEFAULT_VARIANT_ID)
    if variant.direct_main_tool_use:
        return "\n".join([
            "# Workspace State Attachment",
            f"workspace_path: {ctx.workspace_path}",
            f"variant: {variant.id} · {variant.name}",
            "This is a direct single-agent session. Do not create or enter HarnessingTS nodes.",
            "",
            "## Current Workspace Progress",
            "```json",
            json.dumps(progress or {}, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
        ])
    return _render_template(read_prompt_text("main/attachment.md"), {
        "workspace_path": ctx.workspace_path,
        "progress_json": json.dumps(progress or {}, ensure_ascii=False, indent=2, sort_keys=True),
    })


def build_node_system_prompt(
    node_type: NodeType,
    ctx: PromptContext,
    variant: AblationVariant | None = None,
) -> str:
    variant = variant or get_variant(DEFAULT_VARIANT_ID)
    spec = get_node_spec(node_type)
    chunks = [
        _role_kernel(),
        _workspace_static(ctx),
        "\n".join([
            f"## Active Node: {spec.type}",
            f"Purpose: {variant.node_purpose(spec.type, spec.purpose)}",
            f"Required inputs: {', '.join(variant.node_requires(spec.type, spec.requires))}",
            f"Required outputs: {', '.join(variant.node_produces(spec.type, spec.produces))}",
            f"Native tools available in this node: {', '.join(build_node_native_tools(node_type, variant=variant))}",
            "",
            read_prompt_text("node/execution-rules.md"),
            "",
            read_prompt_text("node/finish-protocol.md"),
        ]),
        _node_specific_guidance(node_type),
    ]
    overlay = variant.prompt_overlay(node_type)
    if overlay:
        chunks.append(overlay)
    return "\n\n---\n\n".join(chunks)


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
