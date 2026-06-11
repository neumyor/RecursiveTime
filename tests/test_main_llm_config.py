from __future__ import annotations

import json

from fastapi.testclient import TestClient

from harnessing_ts.state.workspace_store import WorkspaceStore


def _build_workspace(tmp_path) -> WorkspaceStore:
    store = WorkspaceStore(tmp_path)
    store.ensure_layout()
    return store


def test_write_main_llm_config_persists_and_merges(tmp_path) -> None:
    store = _build_workspace(tmp_path)

    written = store.write_main_llm_config(
        {
            "authMode": "manual",
            "protocol": "anthropic",
            "model": "deepseek-v4-pro",
            "apiKey": "sk-abcdef1234",
            "baseUrl": "https://api.deepseek.com/anthropic",
            "contextWindow": "200k",
        }
    )
    assert written["model"] == "deepseek-v4-pro"
    assert written["apiKey"] == "sk-abcdef1234"

    raw = json.loads((tmp_path / "config.llm.json").read_text(encoding="utf-8"))
    assert raw["model"] == "deepseek-v4-pro"
    assert raw["apiKey"] == "sk-abcdef1234"
    assert raw["protocol"] == "anthropic"
    assert raw["contextWindow"] == "200k"

    store.write_main_llm_config({"model": "qwen3.6-plus"})
    raw = json.loads((tmp_path / "config.llm.json").read_text(encoding="utf-8"))
    assert raw["model"] == "qwen3.6-plus"
    assert raw["apiKey"] == "sk-abcdef1234"


def test_write_main_llm_config_drops_empty_or_masked_secrets(tmp_path) -> None:
    store = _build_workspace(tmp_path)
    store.write_main_llm_config({"model": "m1", "apiKey": "first-secret"})

    store.write_main_llm_config({"apiKey": ""})
    raw = json.loads((tmp_path / "config.llm.json").read_text(encoding="utf-8"))
    assert raw["apiKey"] == "first-secret"

    store.write_main_llm_config({"apiKey": "****abcd"})
    raw = json.loads((tmp_path / "config.llm.json").read_text(encoding="utf-8"))
    assert raw["apiKey"] == "first-secret"


def test_write_main_llm_config_sanitizes_invalid_values(tmp_path) -> None:
    store = _build_workspace(tmp_path)
    written = store.write_main_llm_config(
        {
            "authMode": "injected-mode",
            "protocol": "fake-protocol",
            "contextWindow": "5m",
            "model": 12345,  # type: ignore[dict-item]
        }
    )
    assert written["authMode"] == "manual"
    assert written["protocol"] is None
    assert written["contextWindow"] is None
    assert written["model"] == ""


def test_post_llm_config_endpoint_round_trips(tmp_path, monkeypatch) -> None:
    from harnessing_ts.server import create_app

    _build_workspace(tmp_path)
    monkeypatch.setenv("TS_HARNESS_WORKSPACE", str(tmp_path))

    client = TestClient(create_app())
    response = client.post(
        "/api/llm-config",
        json={
            "authMode": "manual",
            "protocol": "anthropic",
            "model": "endpoint-test-model",
            "apiKey": "sk-endpoint-key-1",
            "baseUrl": "https://example.com/anthropic",
            "contextWindow": "200k",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["config"]["model"] == "endpoint-test-model"
    assert payload["config"]["config"]["apiKey"].endswith("ey-1")
    assert (tmp_path / "config.llm.json").exists()

    raw = json.loads((tmp_path / "config.llm.json").read_text(encoding="utf-8"))
    assert raw["apiKey"] == "sk-endpoint-key-1"
