from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from harnessing_ts.orchestrator import HarnessOrchestrator
from harnessing_ts.settings.llm import build_sdk_invocation_config, mask_llm_config, mask_sdk_invocation_config, read_effective_llm_config


TaskRunning = Callable[[Any], bool]


def build_bootstrap_payload(
    *,
    orchestrator: HarnessOrchestrator,
    workspace_path: Path,
    dry_run: bool,
    debug_enabled: bool,
    task_running: TaskRunning,
) -> dict[str, Any]:
    return {
        "state": orchestrator.get_state(),
        "timeline": orchestrator.get_timeline(),
        "mainParts": orchestrator.get_main_parts(),
        "nodes": orchestrator.get_node_sessions(),
        "nodePartsById": orchestrator.get_node_parts_by_id(),
        "nodeSpecs": orchestrator.get_node_specs(),
        "fileTree": orchestrator.get_file_tree(),
        "llmConfig": masked_llm_config(workspace_path),
        "runtimeSettings": orchestrator.get_runtime_settings(),
        "knowledgeGraph": orchestrator.get_knowledge_graph(),
        "knowledgeBaseSummary": orchestrator.get_knowledge_base_summary(),
        "knowledgeGraphParts": orchestrator.get_knowledge_graph_parts(),
        "knowledgeGraphBuild": orchestrator.get_knowledge_graph_build_status(),
        "knowledgeGraphLlmConfig": orchestrator.get_knowledge_graph_llm_config(),
        "chainSummary": orchestrator.get_chain_summary(),
        "chainSummaryBuild": orchestrator.get_chain_summary_status(),
        "chainSummaryParts": orchestrator.get_chain_summary_parts(),
        "dryRun": dry_run,
        "debugEnabled": debug_enabled,
        "runtime": _runtime_payload(orchestrator, task_running),
    }


def build_live_payload(
    *,
    orchestrator: HarnessOrchestrator,
    task_running: TaskRunning,
) -> dict[str, Any]:
    return {
        "state": orchestrator.get_state(),
        "timeline": orchestrator.get_timeline(),
        "mainParts": orchestrator.get_main_parts(),
        "nodes": orchestrator.get_node_sessions(),
        "nodePartsById": orchestrator.get_node_parts_by_id(),
        "runtimeSettings": orchestrator.get_runtime_settings(),
        "knowledgeGraph": orchestrator.get_knowledge_graph(),
        "knowledgeBaseSummary": orchestrator.get_knowledge_base_summary(),
        "knowledgeGraphParts": orchestrator.get_knowledge_graph_parts(),
        "knowledgeGraphBuild": orchestrator.get_knowledge_graph_build_status(),
        "knowledgeGraphLlmConfig": orchestrator.get_knowledge_graph_llm_config(),
        "chainSummary": orchestrator.get_chain_summary(),
        "chainSummaryBuild": orchestrator.get_chain_summary_status(),
        "chainSummaryParts": orchestrator.get_chain_summary_parts(),
        "runtime": _runtime_payload(orchestrator, task_running),
    }


def masked_llm_config(workspace_path: Path) -> dict[str, Any]:
    cfg = read_effective_llm_config(workspace_path)
    sdk = build_sdk_invocation_config(cfg)
    return {"config": mask_llm_config(cfg), "sdk": mask_sdk_invocation_config(sdk)}


def _runtime_payload(orchestrator: HarnessOrchestrator, task_running: TaskRunning) -> dict[str, Any]:
    return {
        "running": task_running(getattr(orchestrator, "_server_run_task", None)),
        "knowledgeGraphRunning": task_running(getattr(orchestrator, "_server_knowledge_graph_task", None)),
        "chainSummaryRunning": task_running(getattr(orchestrator, "_server_chain_summary_task", None)),
        "workspaceUv": orchestrator.get_runtime_status(),
    }
