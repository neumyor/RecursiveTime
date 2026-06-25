from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_TS = ROOT / "frontend" / "src" / "main.ts"


def test_frontend_uses_sse_without_snapshot_polling() -> None:
    source = MAIN_TS.read_text()

    assert "new EventSource('/api/events')" in source
    assert "fetchJson<Bootstrap>('/api/live')" not in source
    assert "fetchJson<Bootstrap>('/api/bootstrap')" not in source
    assert "setInterval(" not in source
    assert "livePoll" not in source


def test_chat_uses_keyed_incremental_dom_reconciliation() -> None:
    source = MAIN_TS.read_text()

    assert "data-message-key" in source
    assert "messageFingerprint" in source
    assert "function createMessageElement" in source
    assert "function renderStable" in source
    assert "els.chatStream.innerHTML = renderedParts.map" not in source


def test_knowledge_graph_sse_snapshot_updates_all_live_panels() -> None:
    source = MAIN_TS.read_text()

    assert "eventType === 'knowledge_graph_snapshot'" in source
    assert "state.bootstrap.knowledgeGraph = payload.knowledgeGraph" in source
    assert "state.bootstrap.knowledgeBaseSummary = payload.knowledgeBaseSummary" in source
    assert "state.bootstrap.knowledgeGraphBuild = payload.knowledgeGraphBuild" in source


def test_interrupt_settling_does_not_leave_permanent_loading_message() -> None:
    source = MAIN_TS.read_text()

    assert "await waitForBackendIdle(5000)" in source
    assert "Pause has already been recorded" in source
    assert "state.loadingMessage = null" in source
    assert "alreadyPaused" in (ROOT / "backend" / "harnessing_ts" / "orchestrator.py").read_text()
