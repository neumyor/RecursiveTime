from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from harnessing_ts.node_state import NodeStateMachine
from harnessing_ts.prompts.compose import PromptContext, build_main_system_prompt, build_node_system_prompt
from harnessing_ts.tools.compose_tools import build_main_allowed_tools, build_node_allowed_tools
from harnessing_ts.variants import DEFAULT_VARIANT_ID, canonical_variant_id, get_variant, resolve_variant


FULL = DEFAULT_VARIANT_ID
RQA_FULL = "NOD-RQA-KTL-CRV-SUB-ADA"
RQA_NO_CASE = "NOD-RQA-KTL-SUB-ADA"
RQA_NO_TOOLS = "NOD-RQA-CRV-SUB-ADA"
RQA_NO_CASE_NO_TOOLS = "NOD-RQA-SUB-ADA"
DIRECT = "DIR"


def test_variant_registry_exposes_feature_code_profiles_and_legacy_aliases(monkeypatch) -> None:
    monkeypatch.delenv("TS_HARNESS_VARIANT", raising=False)
    assert resolve_variant().id == FULL
    assert [get_variant(f"v{index}").id for index in range(6)] == [
        FULL,
        RQA_FULL,
        RQA_NO_CASE,
        RQA_NO_TOOLS,
        RQA_NO_CASE_NO_TOOLS,
        DIRECT,
    ]
    assert get_variant("RQA-NOD-KTL-SUB-ADA").id == RQA_NO_CASE
    assert canonical_variant_id("ADA-SUB-KTL-RQA-NOD") == RQA_NO_CASE
    assert get_variant("rqa-nod-ktl-sub-ada").id == RQA_NO_CASE
    with pytest.raises(RuntimeError, match="unknown feature code"):
        get_variant("NOD-XYZ")
    with pytest.raises(RuntimeError, match="DIR cannot be combined"):
        get_variant("DIR-NOD")
    with pytest.raises(RuntimeError, match="mutually exclusive"):
        get_variant("NOD-KGR-RQA")
    with pytest.raises(RuntimeError, match="syntactically valid but not a registered"):
        get_variant("NOD-RQA")


def test_rebuilt_variant_capabilities_match_ablation_table() -> None:
    v0 = get_variant(FULL)
    v1 = get_variant(RQA_FULL)
    v2 = get_variant(RQA_NO_CASE)
    v3 = get_variant(RQA_NO_TOOLS)
    v4 = get_variant(RQA_NO_CASE_NO_TOOLS)
    v5 = get_variant(DIRECT)

    assert v0.knowledge_graph is True
    assert v0.knowledge_query_source == "graph"
    assert v0.knowledge_to_tools is True
    assert v0.case_review is True

    assert v1.knowledge_graph is False
    assert v1.knowledge_query is True
    assert v1.knowledge_query_source == "references"
    assert v1.knowledge_to_tools is True
    assert v1.case_review is True

    assert v2.knowledge_query_source == "references"
    assert v2.knowledge_to_tools is True
    assert v2.case_review is False

    assert v3.knowledge_query_source == "references"
    assert v3.knowledge_to_tools is False
    assert v3.case_review is True

    assert v4.knowledge_query_source == "references"
    assert v4.knowledge_to_tools is False
    assert v4.case_review is False

    assert v5.node_chain is False
    assert v5.knowledge_query is False
    assert v5.direct_main_tool_use is True


def test_variant_capabilities_change_actual_tool_permissions() -> None:
    assert "mcp__ts_harness__query_knowledge" in build_node_allowed_tools("iterative-solving", variant=get_variant(RQA_FULL))
    assert "mcp__ts_harness__query_knowledge" in build_node_allowed_tools("iterative-solving", variant=get_variant(RQA_NO_TOOLS))
    assert "mcp__ts_harness__query_knowledge" not in build_node_allowed_tools("iterative-solving", variant=get_variant(DIRECT))

    assert "mcp__ts_harness__query_knowledge" in build_main_allowed_tools(variant=get_variant(RQA_FULL))
    assert "mcp__ts_harness__validate_reference_feature_extractor" in build_main_allowed_tools(variant=get_variant(RQA_FULL))
    assert "mcp__ts_harness__validate_reference_feature_extractor" not in build_main_allowed_tools(variant=get_variant(RQA_NO_TOOLS))
    assert "mcp__ts_harness__enter_node" not in build_main_allowed_tools(variant=get_variant(DIRECT))
    assert "Bash" in build_main_allowed_tools(variant=get_variant(DIRECT))


def test_variant_prompt_overlays_are_composed_without_changing_full_profile() -> None:
    context = PromptContext("/tmp/workspace")
    v0_main = build_main_system_prompt(context, get_variant(FULL))
    v1_node = build_node_system_prompt("iterative-solving", context, get_variant(RQA_FULL))
    v2_node = build_node_system_prompt("iterative-solving", context, get_variant(RQA_NO_CASE))
    v3_node = build_node_system_prompt("iterative-solving", context, get_variant(RQA_NO_TOOLS))
    v5_main = build_main_system_prompt(context, get_variant(DIRECT))

    assert "## Node Chain" in v0_main
    assert "direct reference QA" in v1_node
    assert "No Knowledge Graph + No Case Review" in v2_node
    assert "No Knowledge Graph + No Knowledge Tools" in v3_node
    assert "## Node Chain" not in v5_main
    assert "Single-Agent Tool Use" in v5_main


def test_no_case_review_variants_remove_only_case_review_finish_artifact(tmp_path) -> None:
    output_paths = [
        "reports/iterations/001-candidate-review.md",
        "reports/iterations/001-summary.md",
        "user/iteration-state.md",
    ]
    full_output_paths = [
        "reports/iterations/001-candidate-review.md",
        "reports/iterations/001-case-review.md",
        "reports/iterations/001-summary.md",
        "user/iteration-state.md",
    ]
    NodeStateMachine(tmp_path, get_variant(RQA_NO_CASE)).validate_iterative_output_paths(output_paths)
    NodeStateMachine(tmp_path, get_variant(RQA_NO_CASE_NO_TOOLS)).validate_iterative_output_paths(output_paths)

    with pytest.raises(RuntimeError, match="disables case review"):
        NodeStateMachine(tmp_path, get_variant(RQA_NO_CASE)).validate_iterative_output_paths(full_output_paths)
    with pytest.raises(RuntimeError, match="disables case review"):
        NodeStateMachine(tmp_path, get_variant(RQA_NO_CASE_NO_TOOLS)).validate_iterative_output_paths(full_output_paths)

    with pytest.raises(RuntimeError, match="case review"):
        NodeStateMachine(tmp_path, get_variant(RQA_FULL)).validate_iterative_output_paths(output_paths)


def test_single_agent_variant_disables_nodes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TS_HARNESS_VARIANT", DIRECT)
    from harnessing_ts.orchestrator import HarnessOrchestrator

    orchestrator = HarnessOrchestrator(tmp_path, dry_run=True)
    state = orchestrator.initialize()

    assert orchestrator.get_variant()["id"] == DIRECT
    assert state["variantId"] == DIRECT
    assert orchestrator.get_node_specs() == []
    progress = orchestrator._main_progress_snapshot()
    assert progress["recommendedAction"] == "direct_tool_use"
    assert progress["recommendedNode"] is None
    with pytest.raises(RuntimeError, match="disables the HarnessingTS node chain"):
        asyncio.run(orchestrator.request_enter_node({"nodeType": "problem-contract"}))


def test_rqa_variant_disables_graph_builder_but_allows_reference_query_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TS_HARNESS_VARIANT", RQA_FULL)
    from harnessing_ts.orchestrator import HarnessOrchestrator

    orchestrator = HarnessOrchestrator(tmp_path, dry_run=False)
    orchestrator.initialize()

    assert orchestrator.get_knowledge_graph() == {}
    assert orchestrator._main_progress_snapshot()["knowledgeQuerySource"] == "references"
    assert orchestrator._main_progress_snapshot()["knowledgeQueryReady"] is True
    knowledge_to_tools_spec = next(spec for spec in orchestrator.get_node_specs() if spec["type"] == "knowledge-to-tools")
    assert knowledge_to_tools_spec["requires"] == [
        "user/problem-contract.md",
        "user/data-spec.md",
        "references/**",
    ]
    with pytest.raises(RuntimeError, match=f"disabled by ablation variant {RQA_FULL}"):
        asyncio.run(orchestrator.build_knowledge_graph())

    with patch("harnessing_ts.orchestrator.answer_reference_query", new=AsyncMock(return_value={"answer": "from refs"})) as query:
        assert asyncio.run(orchestrator.query_knowledge("What matters?"))["answer"] == "from refs"
    query.assert_awaited_once()


def test_knowledge_tools_variants_skip_knowledge_to_tools_node_and_disable_validate_tool(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TS_HARNESS_VARIANT", RQA_NO_TOOLS)
    from harnessing_ts.orchestrator import HarnessOrchestrator

    orchestrator = HarnessOrchestrator(tmp_path, dry_run=True)
    orchestrator.initialize()

    capabilities = orchestrator.get_variant()["capabilities"]
    assert capabilities["knowledgeToTools"] is False
    assert capabilities["referenceFeatureExtractor"] is False
    assert [spec["type"] for spec in orchestrator.get_node_specs()] == [
        "problem-contract",
        "iterative-solving",
        "final-summary",
    ]
    assert orchestrator.get_node_specs()[0]["next"] == "iterative-solving"

    with pytest.raises(RuntimeError, match="disables the knowledge-to-tools node"):
        asyncio.run(orchestrator.enter_node({"nodeType": "knowledge-to-tools", "rationale": "should be blocked"}))

    with pytest.raises(RuntimeError, match=f"disabled by ablation variant {RQA_NO_TOOLS}"):
        asyncio.run(orchestrator.request_validate_reference_feature_extractor({}))

    state = NodeStateMachine(tmp_path, get_variant(RQA_NO_TOOLS))
    node: dict = {
        "id": "pc-1",
        "nodeType": "problem-contract",
        "status": "completed",
        "success": True,
        "nextNode": None,
        "nextNodeSpecified": False,
        "loopDecision": None,
        "goalMet": False,
    }
    assert state.next_node_after_completion(node) == "iterative-solving"


def test_full_variant_routes_problem_contract_to_knowledge_to_tools(tmp_path) -> None:
    state = NodeStateMachine(tmp_path, get_variant(FULL))
    node: dict = {
        "id": "pc-1",
        "nodeType": "problem-contract",
        "status": "completed",
        "success": True,
        "nextNode": None,
        "nextNodeSpecified": False,
        "loopDecision": None,
        "goalMet": False,
    }
    assert state.next_node_after_completion(node) == "knowledge-to-tools"
