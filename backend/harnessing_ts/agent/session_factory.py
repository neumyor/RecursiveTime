from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from harnessing_ts.agent.sdk_runner import SdkRunner, SdkRunnerConfig
from harnessing_ts.mcp.server import create_harness_mcp_server
from harnessing_ts.prompts.compose import (
    PromptContext,
    build_main_system_prompt,
    build_node_attachment,
    build_node_system_prompt,
)
from harnessing_ts.schema import NodeSession, NodeType, Part
from harnessing_ts.settings.llm import read_effective_llm_config, build_sdk_invocation_config
from harnessing_ts.state.message_log import MessageLog
from harnessing_ts.tools.compose_tools import build_main_allowed_tools, build_node_allowed_tools
from harnessing_ts.variants import AblationVariant, get_variant


def build_main_runner(
    *,
    workspace_path: Path,
    locale: str,
    log_path: Path,
    enter_node: Callable[[dict[str, Any]], Any] | None,
    query_knowledge: Callable[[dict[str, Any]], Any] | None,
    extract_reference_features: Callable[[dict[str, Any]], Any] | None = None,
    inspect_reference_feature_extractor: Callable[[dict[str, Any]], Any] | None = None,
    validate_reference_feature_extractor: Callable[[dict[str, Any]], Any] | None = None,
    variant: AblationVariant | None = None,
    on_part: Callable[[Part], None] | None = None,
) -> SdkRunner:
    variant = variant or get_variant("V0")
    ctx = PromptContext(str(workspace_path), locale)
    sdk_config = build_sdk_invocation_config(read_effective_llm_config(workspace_path))
    mcp_server = create_harness_mcp_server(
        session_role="main",
        enter_node=enter_node,
        query_knowledge=query_knowledge,
        extract_reference_features=extract_reference_features,
        inspect_reference_feature_extractor=inspect_reference_feature_extractor,
        validate_reference_feature_extractor=validate_reference_feature_extractor,
    )
    if mcp_server is None:
        raise RuntimeError("Claude Code SDK Harness MCP server could not be created.")
    return SdkRunner(SdkRunnerConfig(
        cwd=workspace_path,
        system_prompt=build_main_system_prompt(ctx, variant),
        attachment_text=None,
        allowed_tools=build_main_allowed_tools(
            knowledge_graph_ready=query_knowledge is not None,
            reference_feature_extractor_ready=extract_reference_features is not None,
            variant=variant,
        ),
        model=sdk_config.model,
        env=sdk_config.env,
        extra_args=sdk_config.extra_args,
        mcp_server=mcp_server,
        log=MessageLog(log_path),
        on_part=on_part,
    ))


def build_node_runner(
    *,
    workspace_path: Path,
    locale: str,
    node: NodeSession,
    log_path: Path,
    finish_node: Callable[[dict[str, Any]], Any],
    query_knowledge: Callable[[dict[str, Any]], Any] | None,
    extract_reference_features: Callable[[dict[str, Any]], Any] | None = None,
    inspect_reference_feature_extractor: Callable[[dict[str, Any]], Any] | None = None,
    validate_reference_feature_extractor: Callable[[dict[str, Any]], Any] | None = None,
    record_artifact: Callable[[dict[str, Any]], Any],
    record_run: Callable[[dict[str, Any]], Any],
    get_runtime_settings: Callable[[], Any],
    sample_random_candidates: Callable[[dict[str, Any]], Any] | None = None,
    on_session_id: Callable[[str], None],
    on_part: Callable[[Part], None] | None = None,
    variant: AblationVariant | None = None,
) -> SdkRunner:
    variant = variant or get_variant("V0")
    ctx = PromptContext(str(workspace_path), locale)
    sdk_config = build_sdk_invocation_config(read_effective_llm_config(workspace_path))
    node_type: NodeType = node["nodeType"]
    mcp_server = create_harness_mcp_server(
        session_role="node",
        finish_node=finish_node,
        query_knowledge=query_knowledge,
        extract_reference_features=extract_reference_features,
        inspect_reference_feature_extractor=inspect_reference_feature_extractor,
        validate_reference_feature_extractor=validate_reference_feature_extractor,
        record_artifact=record_artifact,
        record_run=record_run,
        get_runtime_settings=get_runtime_settings,
        sample_random_candidates=sample_random_candidates,
    )
    if mcp_server is None:
        raise RuntimeError("Claude Code SDK MCP server is required for node control but could not be created.")
    return SdkRunner(SdkRunnerConfig(
        cwd=workspace_path,
        system_prompt=build_node_system_prompt(node_type, ctx, variant),
        attachment_text=build_node_attachment(node_type, node.get("inputSummary")),
        allowed_tools=build_node_allowed_tools(
            node_type,
            reference_feature_extractor_ready=extract_reference_features is not None,
            variant=variant,
        ),
        model=sdk_config.model,
        env=sdk_config.env,
        extra_args=sdk_config.extra_args,
        mcp_server=mcp_server,
        log=MessageLog(log_path),
        on_session_id=on_session_id,
        on_part=on_part,
    ))
