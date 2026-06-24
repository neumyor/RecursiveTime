from __future__ import annotations

from harnessing_ts.config.markdown import node_document
from harnessing_ts.schema import NodeType
from harnessing_ts.variants import AblationVariant, get_variant

READ_ONLY = ["Read", "LS", "Glob", "Grep"]
DIRECT_TOOL_USE = [*READ_ONLY, "WebFetch", "WebSearch", "Write", "Edit", "Bash"]
MAIN_POOL = ["mcp__ts_harness__enter_node"]
VALIDATE_REFERENCE_FEATURE_TOOL = "mcp__ts_harness__validate_reference_feature_extractor"
REFERENCE_FEATURE_TOOLS = ["mcp__ts_harness__extract_reference_features", "mcp__ts_harness__inspect_reference_feature_extractor"]
NODE_POOL = ["mcp__ts_harness__finish_node", "mcp__ts_harness__get_runtime_settings", "mcp__ts_harness__record_artifact", "mcp__ts_harness__record_run", "mcp__ts_harness__query_knowledge", *REFERENCE_FEATURE_TOOLS]


def build_main_allowed_tools(
    *,
    knowledge_graph_ready: bool = False,
    reference_feature_extractor_ready: bool = False,
    variant: AblationVariant | None = None,
) -> list[str]:
    variant = variant or get_variant("V0")
    if variant.direct_main_tool_use:
        return sorted(set(DIRECT_TOOL_USE))
    tools = [*READ_ONLY, *MAIN_POOL]
    if knowledge_graph_ready and variant.knowledge_graph:
        tools.append("mcp__ts_harness__query_knowledge")
    if variant.knowledge_to_tools:
        tools.append(VALIDATE_REFERENCE_FEATURE_TOOL)
    if reference_feature_extractor_ready and variant.reference_feature_extractor:
        tools.extend(REFERENCE_FEATURE_TOOLS)
    return sorted(set(tools))


def build_node_allowed_tools(
    node_type: NodeType,
    *,
    reference_feature_extractor_ready: bool = False,
    variant: AblationVariant | None = None,
) -> list[str]:
    variant = variant or get_variant("V0")
    pool = list(NODE_POOL)
    if not variant.knowledge_graph:
        pool.remove("mcp__ts_harness__query_knowledge")
    if not variant.reference_feature_extractor or not reference_feature_extractor_ready:
        pool = [tool for tool in pool if tool not in REFERENCE_FEATURE_TOOLS]
    if variant.random_search:
        pool.append("mcp__ts_harness__sample_random_candidates")
    return sorted(set(build_node_native_tools(node_type, variant=variant) + pool))


def build_node_native_tools(
    node_type: NodeType,
    *,
    variant: AblationVariant | None = None,
) -> list[str]:
    variant = variant or get_variant("V0")
    tools = list(node_document(node_type)["native_tools"])
    if node_type == "iterative-solving" and not variant.independent_subagents:
        tools = [tool for tool in tools if tool != "Task"]
    return tools
