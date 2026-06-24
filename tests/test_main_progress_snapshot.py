from __future__ import annotations

from harnessing_ts.orchestrator import HarnessOrchestrator
from harnessing_ts.prompts.compose import PromptContext, build_main_attachment


def _orchestrator(tmp_path) -> HarnessOrchestrator:
    orchestrator = HarnessOrchestrator(tmp_path, dry_run=True, mode="auto")
    orchestrator.initialize()
    return orchestrator


def _complete_node(
    orchestrator: HarnessOrchestrator,
    node_type: str,
    *,
    next_node: str | None = None,
    next_node_specified: bool = False,
    loop_decision: str | None = None,
) -> dict:
    node = orchestrator.store.create_node_session(node_type)
    node.update({
        "status": "completed",
        "success": True,
        "goalMet": loop_decision == "exit",
        "nextNode": next_node,
        "nextNodeSpecified": next_node_specified,
        "loopDecision": loop_decision,
        "outputPaths": [],
    })
    orchestrator.store.write_node_session(node)
    state = orchestrator.get_state()
    if node_type not in state["completedNodes"]:
        state["completedNodes"].append(node_type)
    orchestrator.store.write_state(state)
    orchestrator.state = orchestrator.store.read_state()
    return node


def test_initial_progress_recommends_problem_contract(tmp_path) -> None:
    snapshot = _orchestrator(tmp_path)._main_progress_snapshot()

    assert snapshot["recommendedAction"] == "enter_node"
    assert snapshot["recommendedNode"] == "problem-contract"
    assert snapshot["pipelineComplete"] is False
    assert snapshot["knowledgeGraphReady"] is False


def test_completed_problem_contract_recommends_knowledge_to_tools(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    _complete_node(orchestrator, "problem-contract")

    snapshot = orchestrator._main_progress_snapshot()

    assert snapshot["recommendedAction"] == "enter_node"
    assert snapshot["recommendedNode"] == "knowledge-to-tools"
    assert snapshot["latestNodeSession"]["nodeType"] == "problem-contract"


def test_iterative_continue_recommends_another_iteration(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    _complete_node(orchestrator, "problem-contract")
    _complete_node(
        orchestrator,
        "iterative-solving",
        next_node="iterative-solving",
        next_node_specified=True,
        loop_decision="continue",
    )

    snapshot = orchestrator._main_progress_snapshot()

    assert snapshot["recommendedAction"] == "enter_node"
    assert snapshot["recommendedNode"] == "iterative-solving"


def test_iterative_exit_recommends_final_summary(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    _complete_node(orchestrator, "problem-contract")
    _complete_node(
        orchestrator,
        "iterative-solving",
        next_node="final-summary",
        next_node_specified=True,
        loop_decision="exit",
    )

    snapshot = orchestrator._main_progress_snapshot()

    assert snapshot["recommendedAction"] == "enter_node"
    assert snapshot["recommendedNode"] == "final-summary"


def test_explicit_none_stops_pipeline_instead_of_using_spec_default(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    _complete_node(
        orchestrator,
        "problem-contract",
        next_node=None,
        next_node_specified=True,
    )

    snapshot = orchestrator._main_progress_snapshot()

    assert snapshot["recommendedAction"] == "pipeline_stopped"
    assert snapshot["recommendedNode"] is None


def test_completed_final_summary_prevents_reentry(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    _complete_node(orchestrator, "final-summary")

    snapshot = orchestrator._main_progress_snapshot()

    assert snapshot["recommendedAction"] == "pipeline_complete"
    assert snapshot["recommendedNode"] is None
    assert snapshot["pipelineComplete"] is True


def test_failed_node_requires_explicit_user_retry(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    node = orchestrator.store.create_node_session("iterative-solving")
    node.update({"status": "failed", "success": False, "summary": "evaluation failed"})
    orchestrator.store.write_node_session(node)

    snapshot = orchestrator._main_progress_snapshot()

    assert snapshot["recommendedAction"] == "retry_failed_node"
    assert snapshot["recommendedNode"] == "iterative-solving"


def test_pending_manual_control_prevents_duplicate_node_entry(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    state = orchestrator.get_state()
    state["pendingControl"] = {
        "id": "control-1",
        "kind": "enter_node",
        "status": "pending",
        "createdAt": "2026-06-20T00:00:00Z",
        "nodeType": "problem-contract",
        "args": {"nodeType": "problem-contract"},
        "message": "waiting for approval",
    }
    orchestrator.store.write_state(state)

    snapshot = orchestrator._main_progress_snapshot()

    assert snapshot["recommendedAction"] == "await_control_approval"
    assert snapshot["recommendedNode"] is None
    assert snapshot["pendingControl"]["id"] == "control-1"


def test_main_attachment_contains_structured_progress_and_routing_rules(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    snapshot = orchestrator._main_progress_snapshot()
    text = build_main_attachment(PromptContext(str(tmp_path), "zh"), snapshot)

    assert '"recommendedAction": "enter_node"' in text
    assert '"recommendedNode": "problem-contract"' in text
    assert "routing source of truth" in text
    assert "{progress_json}" not in text
