from harnessing_ts.orchestrator import HarnessOrchestrator


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
        orchestrator._validate_finish_control("iterative-solving", True, "final-summary", "continue")
    except RuntimeError as exc:
        assert "loopDecision=continue" in str(exc)
    else:
        raise AssertionError("Expected conflicting MCP routing to be rejected.")


def test_iterative_solving_success_requires_structured_mcp_control(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path)

    try:
        orchestrator._validate_finish_control("iterative-solving", True, None, None)
    except RuntimeError as exc:
        assert "requires loopDecision or nextNode" in str(exc)
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
        orchestrator._validate_finish_control("iterative-solving", True, "final-summary", None)
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
        orchestrator._validate_finish_control("iterative-solving", True, "iterative-solving", "continue")
    except RuntimeError as exc:
        assert "recommend_exit: true" in str(exc)
    else:
        raise AssertionError("Expected continue routing to be rejected when iteration-state says exit.")
