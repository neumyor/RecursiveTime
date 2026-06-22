from harnessing_ts.orchestrator import HarnessOrchestrator


def test_knowledge_graph_snapshot_contains_live_graph_summary_and_build_status(tmp_path):
    orchestrator = HarnessOrchestrator(tmp_path, dry_run=True)
    orchestrator.initialize()
    events: list[tuple[str, dict]] = []
    orchestrator.set_realtime_event_sink(lambda event_type, payload: events.append((event_type, payload)))

    orchestrator._emit_knowledge_graph_snapshot()

    event_type, payload = events[-1]
    assert event_type == "knowledge_graph_snapshot"
    assert "knowledgeGraph" in payload
    assert "knowledgeBaseSummary" in payload
    assert "knowledgeGraphBuild" in payload
