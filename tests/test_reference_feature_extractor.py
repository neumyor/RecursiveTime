from __future__ import annotations

import json

import pytest

from harnessing_ts.orchestrator import HarnessOrchestrator
from harnessing_ts.reference_feature_extractor import (
    execute_reference_feature_extractor,
    inspect_reference_feature_extractor,
    validate_reference_feature_extractor,
)
from harnessing_ts.tools.compose_tools import build_main_allowed_tools, build_node_allowed_tools
from harnessing_ts.variants import get_variant


def _write_extractor(root) -> None:
    (root / "references").mkdir(parents=True, exist_ok=True)
    (root / "references" / "guide.md").write_text("PR interval above 200 ms is prolonged.\n", encoding="utf-8")
    (root / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (root / "data" / "raw" / "example.json").write_text('{"pr_ms": 220}\n', encoding="utf-8")
    tool = root / "tools" / "reference-feature-extractor"
    tool.mkdir(parents=True, exist_ok=True)
    evidence = [{"referencePath": "references/guide.md", "section": "PR interval", "quote": "above 200 ms is prolonged"}]
    manifest = {
        "schemaVersion": "1.0",
        "entrypoint": "tools/reference-feature-extractor/extractor.py",
        "inputSchema": {"type": "object", "required": ["pr_ms"]},
        "outputSchema": {"type": "object", "required": ["schemaVersion", "features", "warnings"]},
        "features": [{"name": "PR interval", "description": "Measured PR interval", "evidence": evidence}],
    }
    (tool / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tool / "reference-rules.json").write_text(json.dumps({"features": [{
        **manifest["features"][0],
        "computation": "read pr_ms from the case",
        "judgments": [{"when": "> 200", "label": "PR interval prolonged"}],
    }]}), encoding="utf-8")
    (tool / "README.md").write_text("# PR extractor\n\nInput: `{\"pr_ms\": number}`.\n", encoding="utf-8")
    (tool / "test-cases.json").write_text(
        json.dumps([{
            "input": {"pr_ms": 220},
            "source": {"type": "real_sample", "path": "data/raw/example.json", "caseId": "case-1"},
        }]),
        encoding="utf-8",
    )
    (tool / "extractor.py").write_text(
        """import json
import sys

case = json.load(sys.stdin)
value = float(case["pr_ms"])
evidence = [{"referencePath": "references/guide.md", "section": "PR interval", "quote": "above 200 ms is prolonged"}]
output = {
    "schemaVersion": "1.0",
    "features": [{
        "name": "PR interval",
        "value": value,
        "unit": "ms",
        "judgment": {
            "status": "abnormal" if value > 200 else "normal",
            "label": "PR interval prolonged" if value > 200 else "PR interval not prolonged",
            "rule": "prolonged when PR interval > 200 ms",
        },
        "evidence": evidence,
    }],
    "warnings": [],
}
json.dump(output, sys.stdout, ensure_ascii=False, sort_keys=True)
""",
        encoding="utf-8",
    )


def test_validates_executes_and_inspects_reference_feature_extractor(tmp_path) -> None:
    _write_extractor(tmp_path)

    result = validate_reference_feature_extractor(tmp_path, run_tests=True)
    output = execute_reference_feature_extractor(tmp_path, {"pr_ms": 220})
    inspected = inspect_reference_feature_extractor(tmp_path)

    assert result["ready"] is True
    assert result["testsPassed"] == 1
    assert output["features"][0]["value"] == 220.0
    assert output["features"][0]["judgment"]["label"] == "PR interval prolonged"
    assert "case = json.load" in inspected["source"]
    assert inspected["manifest"]["inputSchema"]["required"] == ["pr_ms"]


def test_rejects_non_deterministic_source(tmp_path) -> None:
    _write_extractor(tmp_path)
    source = tmp_path / "tools" / "reference-feature-extractor" / "extractor.py"
    source.write_text("import random\nprint(random.random())\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="outside the deterministic allowlist"):
        validate_reference_feature_extractor(tmp_path)


def test_rejects_test_cases_without_real_workspace_sample(tmp_path) -> None:
    _write_extractor(tmp_path)
    tool = tmp_path / "tools" / "reference-feature-extractor"
    (tool / "test-cases.json").write_text(json.dumps([{"input": {"pr_ms": 220}}]), encoding="utf-8")

    with pytest.raises(RuntimeError, match="real workspace sample"):
        validate_reference_feature_extractor(tmp_path)


def test_tools_are_only_exposed_when_ready_and_enabled() -> None:
    unavailable = build_main_allowed_tools(reference_feature_extractor_ready=False)
    available = build_main_allowed_tools(reference_feature_extractor_ready=True)
    node_unavailable = build_node_allowed_tools("iterative-solving", reference_feature_extractor_ready=False)
    node_available = build_node_allowed_tools("iterative-solving", reference_feature_extractor_ready=True)

    assert "mcp__ts_harness__extract_reference_features" not in unavailable
    assert "mcp__ts_harness__extract_reference_features" in available
    assert "mcp__ts_harness__inspect_reference_feature_extractor" not in node_unavailable
    assert "mcp__ts_harness__inspect_reference_feature_extractor" in node_available


def test_validate_tool_is_exposed_to_knowledge_to_tools_node() -> None:
    allowed = build_node_allowed_tools("knowledge-to-tools", reference_feature_extractor_ready=False)
    disabled = build_node_allowed_tools(
        "knowledge-to-tools",
        reference_feature_extractor_ready=False,
        variant=get_variant("V7"),
    )

    assert "mcp__ts_harness__validate_reference_feature_extractor" in allowed
    assert "mcp__ts_harness__validate_reference_feature_extractor" not in disabled


def test_reset_chat_preserves_built_reference_feature_tool(tmp_path) -> None:
    orchestrator = HarnessOrchestrator(tmp_path)
    orchestrator.initialize()
    _write_extractor(tmp_path)
    orchestrator.store.write_reference_feature_status({"status": "completed"})

    orchestrator.store.reset_chat()

    assert (tmp_path / "tools" / "reference-feature-extractor" / "extractor.py").exists()
    assert orchestrator.store.is_reference_feature_extractor_ready() is True


def test_validate_mcp_tool_publishes_status_for_main_session(tmp_path) -> None:
    import asyncio

    orchestrator = HarnessOrchestrator(tmp_path, mode="auto")
    orchestrator.initialize()
    _write_extractor(tmp_path)

    result = asyncio.run(orchestrator.request_validate_reference_feature_extractor({"runTests": True}))

    assert result["status"] == "completed"
    assert result["ready"] is True
    assert result["featureCount"] == 1
    assert orchestrator.store.is_reference_feature_extractor_ready() is True


def test_validate_mcp_tool_does_not_refresh_main_runner_during_active_node(tmp_path, monkeypatch) -> None:
    import asyncio

    orchestrator = HarnessOrchestrator(tmp_path, mode="auto")
    state = orchestrator.initialize()
    _write_extractor(tmp_path)
    node = orchestrator.store.create_node_session("knowledge-to-tools")
    node["status"] = "running"
    orchestrator.store.write_node_session(node)
    state["activeNode"] = "knowledge-to-tools"
    state["activeNodeSessionId"] = node["id"]
    orchestrator.store.write_state(state)
    orchestrator.state = state
    orchestrator.main_runner = object()  # type: ignore[assignment]
    refresh_calls = 0

    async def fake_refresh() -> None:
        nonlocal refresh_calls
        refresh_calls += 1

    monkeypatch.setattr(orchestrator, "_refresh_main_runner_for_dynamic_tools", fake_refresh)

    result = asyncio.run(orchestrator.request_validate_reference_feature_extractor({"runTests": True}))

    assert result["status"] == "completed"
    assert result["ready"] is True
    assert refresh_calls == 0
    assert orchestrator.store.is_reference_feature_extractor_ready() is True


def test_validate_mcp_tool_reports_failures_for_incomplete_artifacts(tmp_path) -> None:
    import asyncio

    orchestrator = HarnessOrchestrator(tmp_path, mode="auto")
    orchestrator.initialize()
    (tmp_path / "references").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools" / "reference-feature-extractor").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools" / "reference-feature-extractor" / "extractor.py").write_text("import json\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing required files"):
        asyncio.run(orchestrator.request_validate_reference_feature_extractor({"runTests": True}))

    assert orchestrator.store.is_reference_feature_extractor_ready() is False
    status = orchestrator.store.read_reference_feature_status()
    assert status["status"] == "failed"
