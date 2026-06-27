from __future__ import annotations

import json

import pytest

from harnessing_ts.orchestrator import HarnessOrchestrator
from harnessing_ts.reference_feature_extractor import (
    execute_reference_feature_module,
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
        "pythonApi": {"file": "tools/reference-feature-extractor/extractor.py", "function": "extract_features"},
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
    (tool / "evidence-map.json").write_text(json.dumps({
        "schemaVersion": "1.0",
        "features": [{
            "name": "PR interval",
            "evidence": evidence,
            "measurement": "PR interval",
            "unit": "ms",
            "normalRange": "<= 200 ms",
            "abnormalRule": "> 200 ms",
        }],
    }), encoding="utf-8")
    (tool / "feature-plan.json").write_text(json.dumps({
        "schemaVersion": "1.0",
        "features": [{
            "name": "PR interval",
            "unit": "ms",
            "computation": "Read pr_ms from the input case.",
            "judgmentRules": [{"status": "abnormal", "rule": "pr_ms > 200"}],
            "controlExpectation": "Control/reference samples should usually have PR interval <= 200 ms.",
            "expectedFailureModes": ["Input pr_ms may be missing or non-numeric."],
            "evidence": evidence,
        }],
    }), encoding="utf-8")
    (tool / "evaluation-report.json").write_text(json.dumps({
        "schemaVersion": "1.0",
        "controlCaseCount": 1,
        "cases": [{
            "source": {"type": "real_sample", "path": "data/raw/example.json", "caseId": "case-1"},
            "role": "control",
            "featureStatusCounts": {"abnormal": 1},
            "features": [{
                "name": "PR interval",
                "value": 220,
                "judgmentStatus": "abnormal",
                "judgmentLabel": "PR interval prolonged",
            }],
        }],
        "summary": {
            "controlCaseWarnings": [{
                "caseId": "case-1",
                "message": "Fixture intentionally uses an abnormal PR value.",
            }],
        },
    }), encoding="utf-8")
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

def extract_features(case):
    value = float(case["pr_ms"])
    evidence = [{"referencePath": "references/guide.md", "section": "PR interval", "quote": "above 200 ms is prolonged"}]
    return {
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

if __name__ == "__main__":
    json.dump(extract_features(json.load(sys.stdin)), sys.stdout, ensure_ascii=False, sort_keys=True)
""",
        encoding="utf-8",
    )


def test_validates_executes_and_inspects_reference_feature_extractor(tmp_path) -> None:
    _write_extractor(tmp_path)

    result = validate_reference_feature_extractor(tmp_path, run_tests=True)
    output = execute_reference_feature_extractor(tmp_path, {"pr_ms": 220})
    module_output = execute_reference_feature_module(tmp_path, {"pr_ms": 220})
    inspected = inspect_reference_feature_extractor(tmp_path)

    assert result["ready"] is True
    assert result["testsPassed"] == 1
    assert output["features"][0]["value"] == 220.0
    assert module_output == output
    assert output["features"][0]["judgment"]["label"] == "PR interval prolonged"
    assert "def extract_features" in inspected["source"]
    assert inspected["manifest"]["inputSchema"]["required"] == ["pr_ms"]
    assert inspected["manifest"]["pythonApi"]["function"] == "extract_features"
    assert inspected["featurePlan"]["features"][0]["name"] == "PR interval"
    assert inspected["evaluationReport"]["controlCaseCount"] == 1


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


def test_rejects_missing_quality_planning_artifacts(tmp_path) -> None:
    _write_extractor(tmp_path)
    (tmp_path / "tools" / "reference-feature-extractor" / "evaluation-report.json").unlink()

    with pytest.raises(RuntimeError, match="missing required files"):
        validate_reference_feature_extractor(tmp_path)


def test_rejects_evaluation_report_without_control_case(tmp_path) -> None:
    _write_extractor(tmp_path)
    tool = tmp_path / "tools" / "reference-feature-extractor"
    report = json.loads((tool / "evaluation-report.json").read_text(encoding="utf-8"))
    report["controlCaseCount"] = 0
    report["cases"][0]["role"] = "analysis"
    report["cases"][0]["isControl"] = False
    (tool / "evaluation-report.json").write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(RuntimeError, match="control/reference case"):
        validate_reference_feature_extractor(tmp_path)


def test_rejects_extractor_output_without_warnings_array(tmp_path) -> None:
    _write_extractor(tmp_path)
    source = tmp_path / "tools" / "reference-feature-extractor" / "extractor.py"
    source.write_text(
        """import json
import sys

def extract_features(case):
    value = float(case["pr_ms"])
    evidence = [{"referencePath": "references/guide.md", "section": "PR interval", "quote": "above 200 ms is prolonged"}]
    return {
        "schemaVersion": "1.0",
        "features": [{
            "name": "PR interval",
            "value": value,
            "judgment": {"status": "abnormal", "label": "PR interval prolonged"},
            "evidence": evidence,
        }],
    }

if __name__ == "__main__":
    json.dump(extract_features(json.load(sys.stdin)), sys.stdout)
""",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="missing required keys: warnings"):
        validate_reference_feature_extractor(tmp_path, run_tests=True)


def test_rejects_missing_python_api_manifest(tmp_path) -> None:
    _write_extractor(tmp_path)
    tool = tmp_path / "tools" / "reference-feature-extractor"
    manifest = json.loads((tool / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("pythonApi")
    (tool / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="manifest must define pythonApi"):
        validate_reference_feature_extractor(tmp_path)


def test_accepts_task_specific_output_shape(tmp_path) -> None:
    _write_extractor(tmp_path)
    tool = tmp_path / "tools" / "reference-feature-extractor"
    manifest = json.loads((tool / "manifest.json").read_text(encoding="utf-8"))
    manifest["outputSchema"] = {
        "type": "object",
        "required": ["schemaVersion", "measurements"],
        "properties": {"schemaVersion": {"const": "1.0"}},
    }
    (tool / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    source = tmp_path / "tools" / "reference-feature-extractor" / "extractor.py"
    source.write_text(
        """import json
import sys

def extract_features(case):
    return {"schemaVersion": "1.0", "measurements": {"pr_ms": float(case["pr_ms"])}}

if __name__ == "__main__":
    json.dump(extract_features(json.load(sys.stdin)), sys.stdout, sort_keys=True)
""",
        encoding="utf-8",
    )

    result = validate_reference_feature_extractor(tmp_path, run_tests=True)
    output = execute_reference_feature_module(tmp_path, {"pr_ms": 220})

    assert result["testsPassed"] == 1
    assert output["measurements"]["pr_ms"] == 220.0


def test_rejects_extractor_output_missing_declared_feature(tmp_path) -> None:
    _write_extractor(tmp_path)
    tool = tmp_path / "tools" / "reference-feature-extractor"
    manifest = json.loads((tool / "manifest.json").read_text(encoding="utf-8"))
    evidence = [{"referencePath": "references/guide.md", "section": "PR interval", "quote": "above 200 ms is prolonged"}]
    manifest["features"].append({"name": "Secondary interval", "description": "Second declared feature", "evidence": evidence})
    (tool / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    rules = json.loads((tool / "reference-rules.json").read_text(encoding="utf-8"))
    rules["features"].append({
        "name": "Secondary interval",
        "description": "Second declared feature",
        "computation": "Read the same source field for fixture coverage.",
        "judgments": [{"when": "present", "label": "present"}],
        "evidence": evidence,
    })
    (tool / "reference-rules.json").write_text(json.dumps(rules), encoding="utf-8")
    for filename in ("evidence-map.json", "feature-plan.json"):
        payload = json.loads((tool / filename).read_text(encoding="utf-8"))
        entry = dict(payload["features"][0])
        entry["name"] = "Secondary interval"
        payload["features"].append(entry)
        (tool / filename).write_text(json.dumps(payload), encoding="utf-8")
    report = json.loads((tool / "evaluation-report.json").read_text(encoding="utf-8"))
    report["cases"][0]["features"].append({"name": "Secondary interval", "judgmentStatus": "normal"})
    (tool / "evaluation-report.json").write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing declared features"):
        validate_reference_feature_extractor(tmp_path, run_tests=True)


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
        variant=get_variant("NOD-RQA-CRV-SUB-ADA"),
    )

    assert "mcp__ts_harness__validate_reference_feature_extractor" in allowed
    assert "mcp__ts_harness__validate_reference_feature_extractor" not in disabled


def test_reset_chat_clears_built_reference_feature_tool(tmp_path) -> None:
    orchestrator = HarnessOrchestrator(tmp_path)
    orchestrator.initialize()
    _write_extractor(tmp_path)
    orchestrator.store.write_reference_feature_status({"status": "completed"})

    orchestrator.store.reset_chat()

    assert not (tmp_path / "tools" / "reference-feature-extractor" / "extractor.py").exists()
    assert orchestrator.store.is_reference_feature_extractor_ready() is False
    assert orchestrator.store.read_reference_feature_status()["status"] == "idle"


def test_validate_mcp_tool_publishes_status_for_main_session(tmp_path) -> None:
    import asyncio

    orchestrator = HarnessOrchestrator(tmp_path, mode="auto")
    orchestrator.initialize()
    _write_extractor(tmp_path)
    orchestrator.store.write_reference_feature_status({
        "status": "failed",
        "backendValidationStatus": "pending",
        "determinismVerified": False,
    })

    result = asyncio.run(orchestrator.request_validate_reference_feature_extractor({"runTests": True}))

    assert result["status"] == "completed"
    assert result["ready"] is True
    assert result["featureCount"] == 1
    assert orchestrator.store.is_reference_feature_extractor_ready() is True
    status = orchestrator.store.read_reference_feature_status()
    assert "backendValidationStatus" not in status
    assert "determinismVerified" not in status


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
