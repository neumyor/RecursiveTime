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


def _write_extractor(root) -> None:
    (root / "references").mkdir(parents=True, exist_ok=True)
    (root / "references" / "guide.md").write_text("PR interval above 200 ms is prolonged.\n", encoding="utf-8")
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
    (tool / "test-cases.json").write_text(json.dumps([{"input": {"pr_ms": 220}}]), encoding="utf-8")
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


def test_tools_are_only_exposed_when_ready_and_enabled() -> None:
    unavailable = build_main_allowed_tools(reference_feature_extractor_ready=False)
    available = build_main_allowed_tools(reference_feature_extractor_ready=True)
    node_unavailable = build_node_allowed_tools("iterative-solving", reference_feature_extractor_ready=False)
    node_available = build_node_allowed_tools("iterative-solving", reference_feature_extractor_ready=True)

    assert "mcp__ts_harness__extract_reference_features" not in unavailable
    assert "mcp__ts_harness__extract_reference_features" in available
    assert "mcp__ts_harness__inspect_reference_feature_extractor" not in node_unavailable
    assert "mcp__ts_harness__inspect_reference_feature_extractor" in node_available


def test_feature_builder_has_independent_config_and_defaults_to_graph(tmp_path) -> None:
    orchestrator = HarnessOrchestrator(tmp_path)
    orchestrator.initialize()
    orchestrator.store.write_main_llm_config({"model": "main", "apiKey": "main-key"})
    orchestrator.store.write_knowledge_graph_llm_config({"model": "graph", "apiKey": "graph-key"})

    inherited = orchestrator._reference_feature_llm_config()
    orchestrator.update_reference_feature_llm_config({"model": "feature", "apiKey": "feature-key"})
    independent = orchestrator._reference_feature_llm_config()

    assert inherited.model == "graph"
    assert inherited.apiKey == "graph-key"
    assert independent.model == "feature"
    assert independent.apiKey == "feature-key"


def test_reset_chat_preserves_built_reference_feature_tool(tmp_path) -> None:
    orchestrator = HarnessOrchestrator(tmp_path)
    orchestrator.initialize()
    _write_extractor(tmp_path)
    orchestrator.store.write_reference_feature_status({"status": "completed"})

    orchestrator.store.reset_chat()

    assert (tmp_path / "tools" / "reference-feature-extractor" / "extractor.py").exists()
    assert orchestrator.store.is_reference_feature_extractor_ready() is True
