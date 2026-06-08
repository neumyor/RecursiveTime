from __future__ import annotations

from harnessing_ts.config.markdown import node_document
from harnessing_ts.schema import NodeType

READ_ONLY = ["Read", "LS", "Glob", "Grep"]
MAIN_POOL = ["mcp__ts_harness__enter_node", "mcp__ts_harness__query_knowledge"]
NODE_POOL = ["mcp__ts_harness__finish_node", "mcp__ts_harness__get_runtime_settings", "mcp__ts_harness__record_artifact", "mcp__ts_harness__record_run", "mcp__ts_harness__query_knowledge"]


def build_main_allowed_tools() -> list[str]:
    return sorted(set(READ_ONLY + MAIN_POOL))


def build_node_allowed_tools(node_type: NodeType) -> list[str]:
    return sorted(set(build_node_native_tools(node_type) + NODE_POOL))


def build_node_native_tools(node_type: NodeType) -> list[str]:
    return list(node_document(node_type)["native_tools"])
