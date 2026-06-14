from __future__ import annotations

from fastapi.testclient import TestClient

from harnessing_ts.state.workspace_store import WorkspaceStore


def test_bootstrap_contract_includes_full_static_payload(tmp_path, monkeypatch) -> None:
    from harnessing_ts.server import create_app

    WorkspaceStore(tmp_path).ensure_layout()
    monkeypatch.setenv("TS_HARNESS_WORKSPACE", str(tmp_path))

    response = TestClient(create_app()).get("/api/bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert {
        "state",
        "timeline",
        "mainParts",
        "nodes",
        "nodePartsById",
        "nodeSpecs",
        "fileTree",
        "llmConfig",
        "runtimeSettings",
        "knowledgeGraph",
        "knowledgeBaseSummary",
        "knowledgeGraphParts",
        "knowledgeGraphBuild",
        "knowledgeGraphLlmConfig",
        "dryRun",
        "debugEnabled",
        "runtime",
    }.issubset(payload)
    assert {"running", "knowledgeGraphRunning", "workspaceUv"}.issubset(payload["runtime"])


def test_live_contract_is_incremental_subset(tmp_path, monkeypatch) -> None:
    from harnessing_ts.server import create_app

    WorkspaceStore(tmp_path).ensure_layout()
    monkeypatch.setenv("TS_HARNESS_WORKSPACE", str(tmp_path))

    response = TestClient(create_app()).get("/api/live")

    assert response.status_code == 200
    payload = response.json()
    assert "nodeSpecs" not in payload
    assert "fileTree" not in payload
    assert {
        "state",
        "timeline",
        "mainParts",
        "nodes",
        "nodePartsById",
        "runtimeSettings",
        "knowledgeGraph",
        "knowledgeBaseSummary",
        "knowledgeGraphParts",
        "knowledgeGraphBuild",
        "knowledgeGraphLlmConfig",
        "runtime",
    }.issubset(payload)
