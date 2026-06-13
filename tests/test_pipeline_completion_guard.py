from __future__ import annotations

import asyncio
import json
import time
import uuid

import pytest

from harnessing_ts.orchestrator import HarnessOrchestrator
from harnessing_ts.state.workspace_store import WorkspaceStore


def _make_orchestrator(tmp_path) -> HarnessOrchestrator:
    store = WorkspaceStore(tmp_path)
    store.ensure_layout()
    orch = HarnessOrchestrator(tmp_path, dry_run=True, locale="zh", mode="auto")
    orch.initialize()
    return orch


def _completed_state(store: WorkspaceStore, node_type: str) -> None:
    """Pretend `node_type` finished successfully and was recorded."""
    node = store.create_node_session(node_type, rationale="test", input_summary="test")
    node["status"] = "completed"
    node["success"] = True
    node["goalMet"] = False
    node["summary"] = "done"
    node["nextNode"] = None
    node["loopDecision"] = None
    node["outputPaths"] = []
    store.write_node_session(node)

    state = store.read_state()
    if node_type not in state["completedNodes"]:
        state["completedNodes"].append(node_type)
    store.write_state(state)


def test_is_pipeline_complete_requires_final_summary(tmp_path) -> None:
    orch = _make_orchestrator(tmp_path)
    assert orch._is_pipeline_complete() is False

    _completed_state(orch.store, "problem-contract")
    assert orch._is_pipeline_complete() is False

    _completed_state(orch.store, "iterative-solving")
    assert orch._is_pipeline_complete() is False

    _completed_state(orch.store, "final-summary")
    assert orch._is_pipeline_complete() is True


def test_enter_node_rejected_after_pipeline_completes(tmp_path) -> None:
    """Regression for the multi-hour stale-tool_result bug: once
    final-summary has finished, the harness must refuse any further
    enter_node calls so a delayed MCP tool_result from the main
    session's first enter_node call does not respawn a runner for an
    already-completed node."""
    orch = _make_orchestrator(tmp_path)
    _completed_state(orch.store, "problem-contract")
    _completed_state(orch.store, "iterative-solving")
    _completed_state(orch.store, "final-summary")

    for node_type in ("problem-contract", "iterative-solving", "final-summary"):
        with pytest.raises(RuntimeError, match="pipeline is already complete"):
            asyncio.run(orch.enter_node({
                "nodeType": node_type,
                "rationale": "stale MCP tool_result re-delivery",
                "inputSummary": "should be rejected",
            }))


def test_enter_node_still_allowed_during_running_pipeline(tmp_path) -> None:
    """The guard must not block the normal auto-next flow. While the
    pipeline is still running (no final-summary in completedNodes),
    enter_node must succeed (and not raise the pipeline-complete error)."""
    orch = _make_orchestrator(tmp_path)
    _completed_state(orch.store, "problem-contract")
    # The guard must not block this auto-next step; final-summary is
    # not yet in completedNodes, so the pipeline is not "complete".
    node = asyncio.run(orch.enter_node({
        "nodeType": "iterative-solving",
        "rationale": "auto-next from problem-contract",
        "inputSummary": "carry forward from problem-contract",
    }))
    assert node["nodeType"] == "iterative-solving"
    # dry_run: state.activeNode was set to iterative-solving and the
    # new session is created, but completedNodes is only updated on
    # finish_node. So the guard state is what matters here.
    assert orch._is_pipeline_complete() is False
    # And critically: the guard does NOT fire while the pipeline is
    # still in flight (this is what proves we didn't break auto-next).
    try:
        asyncio.run(orch.enter_node({
            "nodeType": "iterative-solving",
            "rationale": "second auto-next",
            "inputSummary": "another one",
        }))
    except RuntimeError as exc:
        msg = str(exc)
        assert "pipeline is already complete" not in msg, (
            "Guard fired prematurely during an in-flight pipeline: " + msg
        )


def test_close_main_runner_is_idempotent(tmp_path) -> None:
    orch = _make_orchestrator(tmp_path)
    # No-op when no runner exists
    asyncio.run(orch._close_main_runner())
    asyncio.run(orch._close_main_runner())
    assert orch.main_runner is None


def test_close_main_runner_terminates_subprocess_and_records_timeline(tmp_path) -> None:
    orch = _make_orchestrator(tmp_path)
    _completed_state(orch.store, "final-summary")

    class _FakeRunner:
        def __init__(self) -> None:
            self.is_running = True
            self.close_called = False
            self.interrupt_called = False
        async def interrupt(self) -> None:
            self.interrupt_called = True
            self.is_running = False
        async def close(self) -> None:
            self.close_called = True

    fake = _FakeRunner()
    orch.main_runner = fake
    asyncio.run(orch._close_main_runner())

    assert fake.interrupt_called is True
    assert fake.close_called is True
    assert orch.main_runner is None

    events = [
        json.loads(line)
        for line in (tmp_path / "logs" / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(e["type"] == "main_runner_closed" for e in events)


def test_pipeline_complete_message_suggests_reset(tmp_path) -> None:
    """The user-facing error must tell them how to recover."""
    orch = _make_orchestrator(tmp_path)
    _completed_state(orch.store, "problem-contract")
    _completed_state(orch.store, "iterative-solving")
    _completed_state(orch.store, "final-summary")

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(orch.enter_node({
            "nodeType": "problem-contract",
            "rationale": "stale",
            "inputSummary": "stale",
        }))
    msg = str(exc.value)
    assert "Reset Workspace" in msg, (
        "Error must guide the user to the Reset Workspace action; "
        "otherwise they won't know how to recover"
    )
