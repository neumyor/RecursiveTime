import asyncio

from harnessing_ts.orchestrator import HarnessOrchestrator


ITERATIVE_OUTPUTS = [
    "reports/iterations/003-candidate-review.md",
    "reports/iterations/003-case-review.md",
    "reports/iterations/003-summary.md",
    "user/iteration-state.md",
]


def test_iterative_solving_continues_from_mcp_loop_decision(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path)

    next_node = orchestrator._next_node_after_completion({
        "id": "node-1",
        "nodeType": "iterative-solving",
        "status": "completed",
        "success": True,
        "loopDecision": "continue",
        "nextNode": "iterative-solving",
    })

    assert next_node == "iterative-solving"


def test_iterative_solving_exits_from_mcp_loop_decision(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path)

    next_node = orchestrator._next_node_after_completion({
        "id": "node-1",
        "nodeType": "iterative-solving",
        "status": "completed",
        "success": True,
        "loopDecision": "exit",
        "nextNode": "final-summary",
    })

    assert next_node == "final-summary"


def test_iterative_solving_does_not_parse_iteration_state(tmp_path):
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "iteration-state.md").write_text("recommend_exit: true\n", encoding="utf-8")
    orchestrator = HarnessOrchestrator(tmp_path)

    next_node = orchestrator._next_node_after_completion({
        "id": "node-1",
        "nodeType": "iterative-solving",
        "status": "completed",
        "success": True,
        "goalMet": False,
    })

    assert next_node is None


def test_iterative_solving_rejects_conflicting_mcp_control(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path)

    try:
        orchestrator._validate_finish_control("iterative-solving", True, "final-summary", "continue", ITERATIVE_OUTPUTS, False)
    except RuntimeError as exc:
        assert "loopDecision=continue" in str(exc)
    else:
        raise AssertionError("Expected conflicting MCP routing to be rejected.")


def test_iterative_solving_success_requires_structured_mcp_control(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path)

    try:
        orchestrator._validate_finish_control("iterative-solving", True, None, None)
    except RuntimeError as exc:
        assert "requires explicit loopDecision" in str(exc)
    else:
        raise AssertionError("Expected missing MCP routing to be rejected.")


def test_iterative_solving_rejects_exit_when_iteration_state_says_continue(tmp_path):
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "iteration-state.md").write_text(
        '```yaml\nrecommend_exit: false\ncurrent_iteration: "002"\nnext_iteration: "003"\n```\n',
        encoding="utf-8",
    )
    orchestrator = HarnessOrchestrator(tmp_path)

    try:
        orchestrator._validate_finish_control("iterative-solving", True, "final-summary", "exit", ITERATIVE_OUTPUTS, False)
    except RuntimeError as exc:
        assert "recommend_exit: false" in str(exc)
    else:
        raise AssertionError("Expected exit routing to be rejected when iteration-state says continue.")


def test_iterative_solving_rejects_continue_when_iteration_state_says_exit(tmp_path):
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "iteration-state.md").write_text("recommend_exit: true\n", encoding="utf-8")
    orchestrator = HarnessOrchestrator(tmp_path)

    try:
        orchestrator._validate_finish_control("iterative-solving", True, "iterative-solving", "continue", ITERATIVE_OUTPUTS, False)
    except RuntimeError as exc:
        assert "recommend_exit: true" in str(exc)
    else:
        raise AssertionError("Expected continue routing to be rejected when iteration-state says exit.")


def test_iterative_solving_rejects_next_node_only_routing(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path)

    try:
        orchestrator._validate_finish_control("iterative-solving", True, "final-summary", None, ITERATIVE_OUTPUTS, False)
    except RuntimeError as exc:
        assert "requires explicit loopDecision" in str(exc)
    else:
        raise AssertionError("Expected nextNode-only iterative routing to be rejected.")


def test_iterative_solving_rejects_missing_anchor_artifacts(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path)

    try:
        orchestrator._validate_finish_control(
            "iterative-solving",
            True,
            "iterative-solving",
            "continue",
            ["runs/iterations/003/candidates/c1/SUBAGENT_REPORT.md"],
            False,
        )
    except RuntimeError as exc:
        assert "candidate review" in str(exc)
        assert "case review" in str(exc)
        assert "iteration summary" in str(exc)
    else:
        raise AssertionError("Expected incomplete iterative outputPaths to be rejected.")


def test_iterative_solving_rejects_goal_met_true_while_continuing(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path)

    try:
        orchestrator._validate_finish_control("iterative-solving", True, "iterative-solving", "continue", ITERATIVE_OUTPUTS, True)
    except RuntimeError as exc:
        assert "goalMet=true" in str(exc)
    else:
        raise AssertionError("Expected goalMet=true with continue to be rejected.")


def test_rejected_finish_node_does_not_mutate_active_node(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path)
    state = orchestrator.initialize()
    node = orchestrator.store.create_node_session("iterative-solving")
    node["status"] = "running"
    orchestrator.store.write_node_session(node)
    state["activeNode"] = "iterative-solving"
    state["activeNodeSessionId"] = node["id"]
    orchestrator.store.write_state(state)
    orchestrator.active_node_session = node

    try:
        asyncio.run(orchestrator.finish_node({
            "success": True,
            "summary": "premature candidate-only finish",
            "nextNode": "iterative-solving",
            "loopDecision": "continue",
            "outputPaths": ["runs/iterations/003/candidates/c1/SUBAGENT_REPORT.md"],
            "goalMet": False,
        }))
    except RuntimeError as exc:
        assert "missing required outputPaths" in str(exc)
    else:
        raise AssertionError("Expected incomplete finish_node to be rejected.")

    assert orchestrator.active_node_session["status"] == "running"
    assert orchestrator.store.read_node_session(node["id"])["status"] == "running"


def test_node_bound_run_record_overrides_agent_supplied_node_identity(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path)
    orchestrator.initialize()
    node = orchestrator.store.create_node_session("iterative-solving")

    orchestrator.record_run_for_node(
        {
            "runId": "run-1",
            "status": "completed",
            "nodeSessionId": "wrong-node",
            "nodeType": "final-summary",
        },
        node["id"],
        "iterative-solving",
    )

    run_events = [event for event in orchestrator.store.read_timeline() if event["type"] == "run_recorded"]
    assert run_events[-1]["nodeSessionId"] == node["id"]
    assert run_events[-1]["nodeType"] == "iterative-solving"
    assert run_events[-1]["payload"]["nodeSessionId"] == node["id"]
    assert run_events[-1]["payload"]["nodeType"] == "iterative-solving"
