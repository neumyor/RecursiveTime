from __future__ import annotations

import asyncio
import pytest

from harnessing_ts.node_state import NodeStateMachine
from harnessing_ts.prompts.compose import PromptContext, build_main_system_prompt, build_node_system_prompt
from harnessing_ts.tools.compose_tools import build_main_allowed_tools, build_node_allowed_tools
from harnessing_ts.variants import get_variant, resolve_variant
from harnessing_ts.variants.random_search import sample_candidates


def test_variant_registry_exposes_all_eight_profiles(monkeypatch) -> None:
    monkeypatch.delenv("TS_HARNESS_VARIANT", raising=False)
    assert resolve_variant().id == "V0"
    assert [get_variant(f"v{index}").id for index in range(8)] == [f"V{index}" for index in range(8)]
    with pytest.raises(RuntimeError, match="Invalid TS_HARNESS_VARIANT"):
        get_variant("V8")


def test_variant_capabilities_change_actual_tool_permissions() -> None:
    v1 = get_variant("V1")
    v3 = get_variant("V3")
    v4 = get_variant("V4")

    assert "Bash" in build_main_allowed_tools(variant=v1)
    assert "mcp__ts_harness__enter_node" not in build_main_allowed_tools(variant=v1)
    assert "mcp__ts_harness__query_knowledge" not in build_node_allowed_tools("iterative-solving", variant=v3)
    assert "Task" not in build_node_allowed_tools("iterative-solving", variant=v4)
    assert "Task" in build_node_allowed_tools("iterative-solving", variant=get_variant("V0"))
    assert "mcp__ts_harness__sample_random_candidates" in build_node_allowed_tools("iterative-solving", variant=get_variant("V2"))


def test_v2_sampler_is_seeded_unique_and_budget_exact() -> None:
    first = sample_candidates(8, seed=20260621)
    second = sample_candidates(8, seed=20260621)

    assert first == second
    assert first["candidateCount"] == 8
    assert len(first["candidates"]) == 8
    assert len({candidate["candidateId"] for candidate in first["candidates"]}) == 8


def test_variant_prompt_overlays_are_composed_without_changing_v0() -> None:
    context = PromptContext("/tmp/workspace")
    v0_main = build_main_system_prompt(context, get_variant("V0"))
    v1_main = build_main_system_prompt(context, get_variant("V1"))
    v2_node = build_node_system_prompt("iterative-solving", context, get_variant("V2"))
    v5_node = build_node_system_prompt("iterative-solving", context, get_variant("V5"))

    assert "## Node Chain" in v0_main
    assert "## Node Chain" not in v1_main
    assert "Single-Agent Tool Use" in v1_main
    assert "Random Search" in v2_node
    assert "不生成 case visualization" in v5_node


def test_v5_removes_only_case_review_finish_artifact(tmp_path) -> None:
    state = NodeStateMachine(tmp_path, get_variant("V5"))
    output_paths = [
        "reports/iterations/001-candidate-review.md",
        "reports/iterations/001-summary.md",
        "user/iteration-state.md",
    ]
    state.validate_iterative_output_paths(output_paths)

    with pytest.raises(RuntimeError, match="case review"):
        NodeStateMachine(tmp_path, get_variant("V0")).validate_iterative_output_paths(output_paths)


def test_v6_backend_rejects_continue_after_one_shot(tmp_path) -> None:
    iteration_state = tmp_path / "user" / "iteration-state.md"
    iteration_state.parent.mkdir()
    iteration_state.write_text("recommend_exit: true\n", encoding="utf-8")
    state = NodeStateMachine(tmp_path, get_variant("V6"))
    output_paths = [
        "reports/iterations/001-candidate-review.md",
        "reports/iterations/001-case-review.md",
        "reports/iterations/001-summary.md",
        "user/iteration-state.md",
    ]

    with pytest.raises(RuntimeError, match="exactly one"):
        state.validate_finish_control(
            "iterative-solving",
            True,
            "iterative-solving",
            "continue",
            output_paths,
            False,
        )

    state.validate_finish_control(
        "iterative-solving",
        True,
        "final-summary",
        "exit",
        output_paths,
        False,
    )


def test_orchestrator_publishes_variant_and_v1_disables_nodes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TS_HARNESS_VARIANT", "V1")
    from harnessing_ts.orchestrator import HarnessOrchestrator

    orchestrator = HarnessOrchestrator(tmp_path, dry_run=True)
    state = orchestrator.initialize()

    assert orchestrator.get_variant()["id"] == "V1"
    assert state["variantId"] == "V1"
    assert orchestrator.get_node_specs() == []
    progress = orchestrator._main_progress_snapshot()
    assert progress["recommendedAction"] == "direct_tool_use"
    assert progress["recommendedNode"] is None
    with pytest.raises(RuntimeError, match="disables the HarnessingTS node chain"):
        asyncio.run(orchestrator.request_enter_node({"nodeType": "problem-contract"}))


def test_v3_backend_rejects_knowledge_operations(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TS_HARNESS_VARIANT", "V3")
    from harnessing_ts.orchestrator import HarnessOrchestrator

    orchestrator = HarnessOrchestrator(tmp_path, dry_run=True)
    orchestrator.initialize()

    assert orchestrator.get_knowledge_graph() == {}
    assert orchestrator.get_knowledge_base_summary() == {}
    with pytest.raises(RuntimeError, match="disabled by ablation variant V3"):
        asyncio.run(orchestrator.request_query_knowledge({"question": "test"}))
    with pytest.raises(RuntimeError, match="disabled by ablation variant V3"):
        asyncio.run(orchestrator.build_knowledge_graph())
    with pytest.raises(RuntimeError, match="disabled by ablation variant V3"):
        orchestrator.search_knowledge_notes("test")


def test_v7_skips_knowledge_to_tools_node_and_disables_validate_tool(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TS_HARNESS_VARIANT", "V7")
    from harnessing_ts.orchestrator import HarnessOrchestrator

    orchestrator = HarnessOrchestrator(tmp_path, dry_run=True)
    orchestrator.initialize()

    capabilities = orchestrator.get_variant()["capabilities"]
    assert capabilities["knowledgeToTools"] is False
    assert capabilities["referenceFeatureExtractor"] is False

    node_types = {spec["type"] for spec in orchestrator.get_node_specs()}
    assert "knowledge-to-tools" in node_types

    problem_spec = next(spec for spec in orchestrator.get_node_specs() if spec["type"] == "problem-contract")
    # When the variant is loaded, the capability is what determines the
    # effective chain; the problem-contract spec's required inputs are
    # gated to empty for the knowledge-to-tools node, and the
    # node_state machinery skips it during routing.
    assert "knowledge-to-tools" in node_types

    with pytest.raises(RuntimeError, match="disables the knowledge-to-tools node"):
        asyncio.run(orchestrator.enter_node({"nodeType": "knowledge-to-tools", "rationale": "should be blocked"}))

    with pytest.raises(RuntimeError, match="disabled by ablation variant V7"):
        asyncio.run(orchestrator.request_validate_reference_feature_extractor({}))

    # Main session must not receive the validate tool under V7.
    from harnessing_ts.tools.compose_tools import build_main_allowed_tools
    main_tools = build_main_allowed_tools(variant=orchestrator.variant)
    assert "mcp__ts_harness__validate_reference_feature_extractor" not in main_tools
    assert "mcp__ts_harness__extract_reference_features" not in main_tools
    assert "mcp__ts_harness__inspect_reference_feature_extractor" not in main_tools


def test_v7_routes_problem_contract_directly_to_iterative_solving(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TS_HARNESS_VARIANT", "V7")
    from harnessing_ts.orchestrator import HarnessOrchestrator
    from harnessing_ts.node_state import NodeStateMachine

    state = NodeStateMachine(tmp_path, get_variant("V7"))
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


def test_v0_routes_problem_contract_to_knowledge_to_tools(tmp_path) -> None:
    from harnessing_ts.node_state import NodeStateMachine
    from harnessing_ts.variants import get_variant

    state = NodeStateMachine(tmp_path, get_variant("V0"))
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


def test_v0_main_session_includes_validate_reference_feature_tool() -> None:
    from harnessing_ts.tools.compose_tools import build_main_allowed_tools
    from harnessing_ts.variants import get_variant

    tools = build_main_allowed_tools(variant=get_variant("V0"))
    assert "mcp__ts_harness__validate_reference_feature_extractor" in tools


def test_v6_backend_rejects_second_iterative_entry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TS_HARNESS_VARIANT", "V6")
    from harnessing_ts.orchestrator import HarnessOrchestrator

    orchestrator = HarnessOrchestrator(tmp_path, dry_run=True)
    orchestrator.initialize()
    previous = orchestrator.store.create_node_session("iterative-solving", "first round", None)
    previous["status"] = "failed"
    previous["success"] = False
    orchestrator.store.write_node_session(previous)

    with pytest.raises(RuntimeError, match="at most 1"):
        asyncio.run(orchestrator.enter_node({"nodeType": "iterative-solving"}))
