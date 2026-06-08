from harnessing_ts.state.workspace_store import WorkspaceStore


def test_reset_workspace_clears_references_graph_and_run_outputs(tmp_path):
    store = WorkspaceStore(tmp_path)
    store.ensure_layout()
    store.write_runtime_settings({"iterativeCandidateCount": 5})
    store.write_knowledge_graph_llm_config({"model": "graph-model", "apiKey": "secret-key"})
    store.write_state({
        "workspaceId": "old-workspace",
        "workspacePath": str(tmp_path),
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
        "mode": "manual",
        "controlMode": "manual",
        "pendingControl": {"kind": "review"},
        "activeNode": "iterative-solving",
        "activeNodeSessionId": "node-1",
        "completedNodes": ["problem-contract"],
        "contractConfirmed": True,
        "finalSummaryConfirmed": True,
        "runtimeSettings": {"iterativeCandidateCount": 5},
    })

    (tmp_path / "references" / "paper.pdf").write_text("reference", encoding="utf-8")
    legacy_evidence = tmp_path / "knowledge_base" / "evidence_notes" / "E-00001.md"
    legacy_graph = tmp_path / "knowledge_base" / "ontology_graph" / "graph_edges.csv"
    legacy_evidence.parent.mkdir(parents=True, exist_ok=True)
    legacy_graph.parent.mkdir(parents=True, exist_ok=True)
    legacy_evidence.write_text("evidence", encoding="utf-8")
    legacy_graph.write_text("source,target,relation\n", encoding="utf-8")
    (tmp_path / "knowledge_base" / "tables" / "knowledge.csv").write_text("knowledge_id,topic,description,evidence_ids,class_ids,relation_ids,notes\n", encoding="utf-8")
    (tmp_path / "artifacts" / "knowledge-graph.json").write_text("{}", encoding="utf-8")
    (tmp_path / "logs" / "main.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "runs" / "run.txt").write_text("run", encoding="utf-8")
    (tmp_path / "reports" / "report.md").write_text("report", encoding="utf-8")

    state = store.reset_workspace()

    assert state["workspaceId"] != "old-workspace"
    assert state["activeNode"] is None
    assert state["completedNodes"] == []
    assert state["contractConfirmed"] is False
    assert state["finalSummaryConfirmed"] is False
    assert state["runtimeSettings"]["iterativeCandidateCount"] == 5

    assert not (tmp_path / "references" / "paper.pdf").exists()
    assert not (tmp_path / "knowledge_base" / "evidence_notes" / "E-00001.md").exists()
    assert not (tmp_path / "knowledge_base" / "ontology_graph" / "graph_edges.csv").exists()
    assert not (tmp_path / "artifacts" / "knowledge-graph.json").exists()
    assert not (tmp_path / "runs" / "run.txt").exists()
    assert not (tmp_path / "reports" / "report.md").exists()
    assert (tmp_path / "references").is_dir()
    assert (tmp_path / "knowledge_base" / "tables").is_dir()
    assert not (tmp_path / "knowledge_base" / "evidence_notes").exists()
    assert not (tmp_path / "knowledge_base" / "knowledge_notes").exists()
    assert not (tmp_path / "knowledge_base" / "ontology_graph").exists()

    assert store.read_runtime_settings()["iterativeCandidateCount"] == 5
    assert store.read_knowledge_graph_llm_config()["model"] == "graph-model"
    assert store.read_timeline()[-1]["type"] == "workspace_reset"
