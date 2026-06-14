from harnessing_ts.state.workspace_store import WorkspaceStore
from harnessing_ts.orchestrator import HarnessOrchestrator


class _DummyRunner:
    def __init__(self, *, running: bool = False) -> None:
        self._running = running
        self.interrupted = False
        self.closed = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def interrupt(self) -> None:
        self.interrupted = True

    async def close(self) -> None:
        self.closed = True


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


def test_reset_chat_preserves_raw_references_and_knowledge_graph(tmp_path):
    store = WorkspaceStore(tmp_path)
    store.ensure_layout()
    store.write_runtime_settings({"iterativeCandidateCount": 4})
    store.write_state({
        "workspaceId": "old-workspace",
        "workspacePath": str(tmp_path),
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
        "mode": "auto",
        "controlMode": "auto",
        "pendingControl": {"kind": "enter_node"},
        "activeNode": "iterative-solving",
        "activeNodeSessionId": "node-1",
        "completedNodes": ["problem-contract"],
        "contractConfirmed": True,
        "finalSummaryConfirmed": False,
        "runtimeSettings": {"iterativeCandidateCount": 4},
    })

    (tmp_path / "data" / "raw" / "dataset.csv").write_text("raw", encoding="utf-8")
    (tmp_path / "data" / "processed" / "features.csv").write_text("processed", encoding="utf-8")
    (tmp_path / "references" / "paper.pdf").write_text("reference", encoding="utf-8")
    (tmp_path / "knowledge_base" / "tables" / "knowledge.csv").write_text("knowledge_id,topic\nK1,ECG\n", encoding="utf-8")
    (tmp_path / "knowledge_base" / "indexes" / "keyword_index.json").write_text("{}", encoding="utf-8")
    (tmp_path / "artifacts" / "knowledge-graph.json").write_text('{"nodes":[]}', encoding="utf-8")
    (tmp_path / "artifacts" / "scratch.md").write_text("scratch", encoding="utf-8")
    (tmp_path / "state" / "knowledge-graph-build.json").write_text('{"status":"completed"}', encoding="utf-8")
    (tmp_path / "logs" / "knowledge-graph-builder.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "logs" / "main.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "logs" / "nodes" / "node-1.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "state" / "nodes" / "node-1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "user" / "problem-contract.md").write_text("contract", encoding="utf-8")
    (tmp_path / "runs" / "run.txt").write_text("run", encoding="utf-8")
    (tmp_path / "reports" / "report.md").write_text("report", encoding="utf-8")
    (tmp_path / "tools" / "tool.py").write_text("print('x')", encoding="utf-8")

    state = store.reset_chat()

    assert state["workspaceId"] != "old-workspace"
    assert state["controlMode"] == "auto"
    assert state["activeNode"] is None
    assert state["completedNodes"] == []
    assert state["contractConfirmed"] is False
    assert state["runtimeSettings"]["iterativeCandidateCount"] == 4

    assert (tmp_path / "data" / "raw" / "dataset.csv").exists()
    assert (tmp_path / "references" / "paper.pdf").exists()
    assert (tmp_path / "knowledge_base" / "tables" / "knowledge.csv").exists()
    assert (tmp_path / "knowledge_base" / "indexes" / "keyword_index.json").exists()
    assert (tmp_path / "artifacts" / "knowledge-graph.json").exists()
    assert (tmp_path / "state" / "knowledge-graph-build.json").exists()
    assert (tmp_path / "logs" / "knowledge-graph-builder.jsonl").exists()

    assert not (tmp_path / "data" / "processed" / "features.csv").exists()
    assert not (tmp_path / "artifacts" / "scratch.md").exists()
    assert not (tmp_path / "logs" / "main.jsonl").exists()
    assert not (tmp_path / "logs" / "nodes" / "node-1.jsonl").exists()
    assert not (tmp_path / "state" / "nodes" / "node-1.json").exists()
    assert not (tmp_path / "user" / "problem-contract.md").exists()
    assert not (tmp_path / "runs" / "run.txt").exists()
    assert not (tmp_path / "reports" / "report.md").exists()
    assert not (tmp_path / "tools" / "tool.py").exists()

    assert store.read_timeline()[-1]["type"] == "chat_reset"


def test_clear_main_logs_closes_cached_main_runner(tmp_path):
    import asyncio

    orchestrator = HarnessOrchestrator(tmp_path, mode="auto")
    orchestrator.initialize()
    runner = _DummyRunner()
    orchestrator.main_runner = runner  # type: ignore[assignment]

    asyncio.run(orchestrator.clear_debug_logs("main"))

    assert runner.closed is True
    assert orchestrator.main_runner is None
    assert any(
        event.get("type") == "main_runner_closed"
        and event.get("payload", {}).get("reason") == "main_log_cleared"
        for event in orchestrator.store.read_timeline()
    )


def test_reset_workspace_closes_cached_sdk_runners(tmp_path):
    import asyncio

    orchestrator = HarnessOrchestrator(tmp_path, mode="auto")
    orchestrator.initialize()
    main_runner = _DummyRunner(running=True)
    node_runner = _DummyRunner(running=True)
    orchestrator.main_runner = main_runner  # type: ignore[assignment]
    orchestrator.active_node_runner = node_runner  # type: ignore[assignment]

    asyncio.run(orchestrator.clear_debug_logs("all"))

    assert main_runner.interrupted is True
    assert main_runner.closed is True
    assert node_runner.interrupted is True
    assert node_runner.closed is True
    assert orchestrator.main_runner is None
    assert orchestrator.active_node_runner is None
    assert orchestrator.state is not None
    assert orchestrator.state["activeNode"] is None


def test_reset_chat_closes_cached_sdk_runners(tmp_path):
    import asyncio

    orchestrator = HarnessOrchestrator(tmp_path, mode="auto")
    orchestrator.initialize()
    main_runner = _DummyRunner(running=True)
    node_runner = _DummyRunner(running=True)
    orchestrator.main_runner = main_runner  # type: ignore[assignment]
    orchestrator.active_node_runner = node_runner  # type: ignore[assignment]

    asyncio.run(orchestrator.clear_debug_logs("chat"))

    assert main_runner.interrupted is True
    assert main_runner.closed is True
    assert node_runner.interrupted is True
    assert node_runner.closed is True
    assert orchestrator.main_runner is None
    assert orchestrator.active_node_runner is None
    assert orchestrator.state is not None
    assert orchestrator.state["activeNode"] is None
