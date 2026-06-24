from __future__ import annotations

import asyncio

import pytest

from harnessing_ts.orchestrator import HarnessOrchestrator


ITERATIVE_OUTPUTS = [
    "reports/iterations/003-candidate-review.md",
    "reports/iterations/003-case-review.md",
    "reports/iterations/003-summary.md",
    "user/iteration-state.md",
]


def _orchestrator(tmp_path, *, mode: str) -> HarnessOrchestrator:
    orchestrator = HarnessOrchestrator(tmp_path, dry_run=True, mode=mode)
    orchestrator.initialize()
    return orchestrator


def _activate_node(orchestrator: HarnessOrchestrator, node_type: str):
    state = orchestrator.get_state()
    node = orchestrator.store.create_node_session(node_type)
    node["status"] = "running"
    orchestrator.store.write_node_session(node)
    state["activeNode"] = node_type
    state["activeNodeSessionId"] = node["id"]
    orchestrator.store.write_state(state)
    orchestrator.state = orchestrator.store.read_state()
    orchestrator.active_node_session = node
    return node


def test_manual_enter_node_parks_pending_control_without_mutating_active_node(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="manual")

    result = asyncio.run(orchestrator.request_enter_node({
        "nodeType": "problem-contract",
        "rationale": "start workflow",
        "inputSummary": "user request",
    }))

    state = orchestrator.get_state()
    assert result["status"] == "pending_human_decision"
    assert state["activeNode"] is None
    assert state["activeNodeSessionId"] is None
    assert state["pendingControl"]["kind"] == "enter_node"
    assert state["pendingControl"]["nodeType"] == "problem-contract"


def test_manual_approve_enter_node_starts_dry_run_node(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="manual")
    asyncio.run(orchestrator.request_enter_node({
        "nodeType": "problem-contract",
        "rationale": "start workflow",
        "inputSummary": "user request",
    }))

    result = asyncio.run(orchestrator.approve_pending_control())

    state = orchestrator.get_state()
    assert result["approved"] is True
    assert state["pendingControl"] is None
    assert state["activeNode"] == "problem-contract"
    assert state["activeNodeSessionId"] == result["result"]["id"]
    assert orchestrator.store.read_node_session(result["result"]["id"])["status"] == "running"


def test_manual_finish_node_parks_request_and_marks_node_waiting_approval(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="manual")
    node = _activate_node(orchestrator, "problem-contract")

    result = asyncio.run(orchestrator.request_finish_node({
        "success": True,
        "summary": "contract complete",
        "goalMet": True,
        "nextNode": "iterative-solving",
        "outputPaths": ["user/problem-contract.md", "user/data-spec.md"],
    }))

    state = orchestrator.get_state()
    persisted = orchestrator.store.read_node_session(node["id"])
    assert result["status"] == "pending_human_decision"
    assert state["activeNode"] == "problem-contract"
    assert state["pendingControl"]["kind"] == "finish_node"
    assert state["pendingControl"]["nodeSessionId"] == node["id"]
    assert persisted["status"] == "waiting_approval"


def test_manual_approve_finish_node_parks_next_enter_request(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="manual")
    node = _activate_node(orchestrator, "problem-contract")
    asyncio.run(orchestrator.request_finish_node({
        "success": True,
        "summary": "contract complete",
        "goalMet": True,
        "nextNode": "iterative-solving",
        "outputPaths": ["user/problem-contract.md", "user/data-spec.md"],
    }))

    result = asyncio.run(orchestrator.approve_pending_control())

    state = orchestrator.get_state()
    persisted = orchestrator.store.read_node_session(node["id"])
    assert result["approved"] is True
    assert persisted["status"] == "completed"
    assert state["activeNode"] is None
    assert state["activeNodeSessionId"] is None
    assert state["completedNodes"] == ["problem-contract"]
    assert state["pendingControl"]["kind"] == "enter_node"
    assert state["pendingControl"]["nodeType"] == "iterative-solving"


def test_reject_finish_node_returns_waiting_node_to_paused(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="manual")
    node = _activate_node(orchestrator, "problem-contract")
    asyncio.run(orchestrator.request_finish_node({
        "success": True,
        "summary": "contract complete",
        "goalMet": True,
        "nextNode": "iterative-solving",
        "outputPaths": ["user/problem-contract.md", "user/data-spec.md"],
    }))

    result = orchestrator.reject_pending_control("needs more evidence")

    state = orchestrator.get_state()
    persisted = orchestrator.store.read_node_session(node["id"])
    assert result["rejected"] is True
    assert state["pendingControl"] is None
    assert state["activeNode"] == "problem-contract"
    assert persisted["status"] == "paused"
    assert "needs more evidence" in persisted["summary"]


def test_node_bound_finish_rejects_stale_node_session(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="auto")
    _activate_node(orchestrator, "problem-contract")

    with pytest.raises(RuntimeError, match="finish_node rejected"):
        asyncio.run(orchestrator.request_finish_node_for_node({
            "success": True,
            "summary": "stale finish",
        }, "stale-node-id"))


def test_auto_successful_problem_contract_finish_enters_next_node(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="auto")
    node = _activate_node(orchestrator, "problem-contract")

    result = asyncio.run(orchestrator.finish_node({
        "success": True,
        "summary": "contract complete",
        "goalMet": True,
        "nextNode": "iterative-solving",
        "outputPaths": ["user/problem-contract.md", "user/data-spec.md"],
    }))

    state = orchestrator.get_state()
    assert result["nextNode"] == "iterative-solving"
    assert orchestrator.store.read_node_session(node["id"])["status"] == "completed"
    assert state["activeNode"] is None
    assert state["completedNodes"] == ["problem-contract"]

    asyncio.run(orchestrator._maybe_auto_enter_next_node(orchestrator.store.read_node_session(node["id"])))
    state = orchestrator.get_state()
    assert state["activeNode"] == "iterative-solving"
    assert any(event["type"] == "auto_next" for event in orchestrator.store.read_timeline())


def test_auto_failed_finish_does_not_offer_or_enter_next_node(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="auto")
    node = _activate_node(orchestrator, "problem-contract")

    result = asyncio.run(orchestrator.finish_node({
        "success": False,
        "summary": "contract failed",
        "goalMet": False,
        "nextNode": "iterative-solving",
        "outputPaths": [],
    }))

    state = orchestrator.get_state()
    assert result["nextNode"] is None
    assert orchestrator.store.read_node_session(node["id"])["status"] == "failed"
    assert state["activeNode"] is None
    assert state["completedNodes"] == []

    asyncio.run(orchestrator._maybe_auto_enter_next_node(orchestrator.store.read_node_session(node["id"])))
    assert orchestrator.get_state()["activeNode"] is None
    assert not any(event["type"] == "auto_next" for event in orchestrator.store.read_timeline())


def test_omitted_next_node_uses_node_spec_default(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="auto")
    node = _activate_node(orchestrator, "problem-contract")

    result = asyncio.run(orchestrator.finish_node({
        "success": True,
        "summary": "contract complete",
        "goalMet": False,
        "outputPaths": ["user/problem-contract.md", "user/data-spec.md"],
    }))

    persisted = orchestrator.store.read_node_session(node["id"])
    assert persisted["nextNodeSpecified"] is False
    assert result["nextNode"] == "knowledge-to-tools"


def test_null_next_node_uses_node_spec_default(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="auto")
    node = _activate_node(orchestrator, "problem-contract")

    result = asyncio.run(orchestrator.finish_node({
        "success": True,
        "summary": "contract complete",
        "goalMet": False,
        "nextNode": None,
        "outputPaths": ["user/problem-contract.md", "user/data-spec.md"],
    }))

    persisted = orchestrator.store.read_node_session(node["id"])
    assert persisted["nextNodeSpecified"] is False
    assert result["nextNode"] == "knowledge-to-tools"


def test_explicit_none_next_node_stops_successful_ordinary_node(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="auto")
    node = _activate_node(orchestrator, "problem-contract")

    result = asyncio.run(orchestrator.finish_node({
        "success": True,
        "summary": "contract complete but stop requested",
        "goalMet": False,
        "nextNode": "none",
        "outputPaths": ["user/problem-contract.md", "user/data-spec.md"],
    }))

    persisted = orchestrator.store.read_node_session(node["id"])
    assert persisted["nextNode"] is None
    assert persisted["nextNodeSpecified"] is True
    assert result["nextNode"] is None


def test_explicit_next_node_overrides_node_spec_default(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="auto")
    node = _activate_node(orchestrator, "problem-contract")

    result = asyncio.run(orchestrator.finish_node({
        "success": True,
        "summary": "contract complete and summarize directly",
        "goalMet": False,
        "nextNode": "final-summary",
        "outputPaths": ["user/problem-contract.md", "user/data-spec.md"],
    }))

    persisted = orchestrator.store.read_node_session(node["id"])
    assert persisted["nextNodeSpecified"] is True
    assert result["nextNode"] == "final-summary"


def test_enter_node_rejects_when_another_node_is_active(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, mode="auto")
    _activate_node(orchestrator, "problem-contract")

    with pytest.raises(RuntimeError, match="active node problem-contract"):
        asyncio.run(orchestrator.enter_node({
            "nodeType": "iterative-solving",
            "rationale": "should not start",
        }))
