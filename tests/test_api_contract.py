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
        "variant",
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
        "referenceFeatureBuild",
        "referenceFeatureTool",
        "referenceFeatureParts",
        "chainSummary",
        "chainSummaryBuild",
        "chainSummaryParts",
        "dryRun",
        "debugEnabled",
        "runtime",
    }.issubset(payload)
    assert {"running", "knowledgeGraphRunning", "chainSummaryRunning", "workspaceUv"}.issubset(payload["runtime"])
    assert payload["variant"]["id"] == "NOD-KGR-KTL-CRV-SUB-ADA"
    assert payload["variant"]["features"] == ["NOD", "KGR", "KTL", "CRV", "SUB", "ADA"]


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
        "variant",
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
        "referenceFeatureBuild",
        "referenceFeatureTool",
        "referenceFeatureParts",
        "chainSummary",
        "chainSummaryBuild",
        "chainSummaryParts",
        "runtime",
    }.issubset(payload)


def test_realtime_sse_endpoint_is_registered(tmp_path, monkeypatch) -> None:
    from harnessing_ts.server import create_app

    WorkspaceStore(tmp_path).ensure_layout()
    monkeypatch.setenv("TS_HARNESS_WORKSPACE", str(tmp_path))

    app = create_app()
    routes = {getattr(route, "path", "") for route in app.routes}

    assert "/api/events" in routes
    assert "/api/reference-features/status" in routes
    assert "/api/reference-features/tool" in routes
    assert "/api/reference-features/run" in routes
    # The standalone build/pause/llm-config endpoints are gone; the
    # main session now builds the tool directly via the
    # validate_reference_feature_extractor MCP tool.
    assert "/api/reference-features/build" not in routes
    assert "/api/reference-features/llm-config" not in routes
