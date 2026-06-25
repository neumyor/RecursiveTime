from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from harnessing_ts.config.markdown import read_prompt_text
from harnessing_ts.state.jsonl import read_json


TOOL_DIR = Path("tools/reference-feature-extractor")
MANIFEST_PATH = TOOL_DIR / "manifest.json"
SOURCE_PATH = TOOL_DIR / "extractor.py"
RULES_PATH = TOOL_DIR / "reference-rules.json"
README_PATH = TOOL_DIR / "README.md"
TEST_CASES_PATH = TOOL_DIR / "test-cases.json"
EVIDENCE_MAP_PATH = TOOL_DIR / "evidence-map.json"
FEATURE_PLAN_PATH = TOOL_DIR / "feature-plan.json"
EVALUATION_REPORT_PATH = TOOL_DIR / "evaluation-report.json"
REFERENCE_FEATURE_ARTIFACT_PATHS = (
    MANIFEST_PATH,
    SOURCE_PATH,
    RULES_PATH,
    README_PATH,
    TEST_CASES_PATH,
    EVIDENCE_MAP_PATH,
    FEATURE_PLAN_PATH,
    EVALUATION_REPORT_PATH,
)
KNOWLEDGE_TO_TOOLS_REQUIRED_OUTPUT_PATHS = tuple(str(path) for path in REFERENCE_FEATURE_ARTIFACT_PATHS) + (
    "state/reference-feature-build.json",
)

# The reference feature extractor is now built directly by the main
# session during the knowledge-to-tools node. The prompt below is the
# authoritative build instructions; the main agent reads it (or its
# inlined summary in the node guidance) and writes the artifacts with
# Read/LS/Glob/Grep/Write/Edit/Bash. After writing, the main session
# calls the validate_reference_feature_extractor MCP tool, which
# invokes validate_reference_feature_extractor() below. The actual
# build is not driven from this module anymore.
BUILDER_SYSTEM_PROMPT_PATH = "reference-feature-extractor/system.md"
BUILDER_BUILD_PROMPT_PATH = "reference-feature-extractor/build.md"

_ALLOWED_IMPORTS = {
    "json", "sys", "math", "statistics", "decimal", "fractions", "collections",
    "itertools", "functools", "typing", "dataclasses", "re", "numpy", "scipy",
}
_FORBIDDEN_CALLS = {"eval", "exec", "compile", "open", "input", "breakpoint", "__import__"}
_FORBIDDEN_ATTRS = {"system", "popen", "spawn", "fork", "urandom", "random", "default_rng", "rand", "randn"}


def builder_system_prompt() -> str:
    return read_prompt_text(BUILDER_SYSTEM_PROMPT_PATH)


def builder_build_prompt(*, task_files: list[str], references: list[str]) -> str:
    template = read_prompt_text(BUILDER_BUILD_PROMPT_PATH)
    return template.replace("{references_json}", json.dumps(references, ensure_ascii=False, indent=2)).replace(
        "{task_files_json}", json.dumps(task_files, ensure_ascii=False, indent=2)
    )


def validate_reference_feature_extractor(workspace_path: Path, *, run_tests: bool = False) -> dict[str, Any]:
    tool_dir = workspace_path / TOOL_DIR
    required = list(REFERENCE_FEATURE_ARTIFACT_PATHS)
    missing = [str(path) for path in required if not (workspace_path / path).is_file()]
    if missing:
        raise RuntimeError("Reference feature extractor is missing required files: " + ", ".join(missing))
    resolved_tool_dir = tool_dir.resolve()
    for path in required:
        resolved = (workspace_path / path).resolve()
        if resolved_tool_dir not in resolved.parents or (workspace_path / path).is_symlink():
            raise RuntimeError(f"Reference feature artifact must be a regular file inside {TOOL_DIR}: {path}")

    manifest = read_json(workspace_path / MANIFEST_PATH)
    rules = read_json(workspace_path / RULES_PATH)
    tests = read_json(workspace_path / TEST_CASES_PATH)
    evidence_map = read_json(workspace_path / EVIDENCE_MAP_PATH)
    feature_plan = read_json(workspace_path / FEATURE_PLAN_PATH)
    evaluation_report = read_json(workspace_path / EVALUATION_REPORT_PATH)
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != "1.0":
        raise RuntimeError("manifest.json must be an object with schemaVersion=1.0.")
    if manifest.get("entrypoint") != str(SOURCE_PATH):
        raise RuntimeError(f"manifest entrypoint must be {SOURCE_PATH}.")
    if not isinstance(manifest.get("inputSchema"), dict) or not isinstance(manifest.get("outputSchema"), dict):
        raise RuntimeError("manifest must define task-specific inputSchema and outputSchema objects.")
    if manifest["outputSchema"].get("type") != "object":
        raise RuntimeError("manifest.outputSchema must describe a JSON object.")
    python_api = _validate_python_api_manifest(manifest)
    features = manifest.get("features")
    if not isinstance(features, list) or not features:
        raise RuntimeError("manifest.features must contain at least one feature definition.")
    for feature in features:
        if not isinstance(feature, dict) or not str(feature.get("name", "")).strip():
            raise RuntimeError("Each manifest feature requires a non-empty name.")
        evidence = feature.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise RuntimeError(f"Feature {feature.get('name')} requires reference evidence.")
        for item in evidence:
            _validate_reference_evidence_item(item, workspace_path, f"Feature {feature.get('name')}")
    declared_feature_names = [str(feature.get("name")) for feature in features]
    _validate_evidence_map(evidence_map, declared_feature_names, workspace_path)
    _validate_feature_plan(feature_plan, declared_feature_names, workspace_path)
    _validate_evaluation_report(evaluation_report, declared_feature_names, workspace_path)
    if not isinstance(rules, dict) or not isinstance(rules.get("features"), list):
        raise RuntimeError("reference-rules.json must contain a features array.")
    rule_names = set()
    for rule in rules["features"]:
        if not isinstance(rule, dict) or not str(rule.get("name", "")).strip():
            raise RuntimeError("Each reference rule requires a name.")
        if not str(rule.get("computation", "")).strip() or not isinstance(rule.get("judgments"), list):
            raise RuntimeError(f"Reference rule {rule.get('name')} requires computation and judgments.")
        if not isinstance(rule.get("evidence"), list) or not rule["evidence"]:
            raise RuntimeError(f"Reference rule {rule.get('name')} requires evidence.")
        rule_names.add(str(rule["name"]))
    missing_rules = [str(feature.get("name")) for feature in features if str(feature.get("name")) not in rule_names]
    if missing_rules:
        raise RuntimeError("Features missing from reference-rules.json: " + ", ".join(missing_rules))
    if not isinstance(tests, list) or not tests:
        raise RuntimeError("test-cases.json must contain at least one deterministic example.")
    if not any(_is_real_sample_test_case(workspace_path, case) for case in tests if isinstance(case, dict)):
        raise RuntimeError(
            "test-cases.json must contain at least one real workspace sample with "
            "source.type=real_sample and an existing workspace-relative source.path."
        )

    source = (workspace_path / SOURCE_PATH).read_text(encoding="utf-8")
    _validate_deterministic_source(source)
    _load_python_api(workspace_path, python_api)
    result = {
        "ready": True,
        "toolDir": str(TOOL_DIR),
        "manifestPath": str(MANIFEST_PATH),
        "sourcePath": str(SOURCE_PATH),
        "readmePath": str(README_PATH),
        "evidenceMapPath": str(EVIDENCE_MAP_PATH),
        "featurePlanPath": str(FEATURE_PLAN_PATH),
        "evaluationReportPath": str(EVALUATION_REPORT_PATH),
        "featureCount": len(features),
        "features": [str(item.get("name")) for item in features],
        "pythonApi": python_api,
    }
    if run_tests:
        checked = 0
        for index, case in enumerate(tests):
            if not isinstance(case, dict) or "input" not in case:
                raise RuntimeError(f"test-cases.json item {index} requires input.")
            first = execute_reference_feature_extractor(workspace_path, case["input"])
            second = execute_reference_feature_extractor(workspace_path, case["input"])
            if first != second:
                raise RuntimeError(f"Extractor is non-deterministic for test case {index}.")
            if "expected" in case and first != case["expected"]:
                raise RuntimeError(f"Extractor output does not match expected output for test case {index}.")
            module_first = execute_reference_feature_module(workspace_path, case["input"])
            module_second = execute_reference_feature_module(workspace_path, case["input"])
            if module_first != module_second:
                raise RuntimeError(f"Extractor Python API is non-deterministic for test case {index}.")
            if module_first != first:
                raise RuntimeError(f"Extractor Python API output differs from CLI output for test case {index}.")
            checked += 1
        result["testsPassed"] = checked
    return result


def _validate_evidence_map(evidence_map: Any, declared_feature_names: list[str], workspace_path: Path) -> None:
    if not isinstance(evidence_map, dict) or evidence_map.get("schemaVersion") != "1.0":
        raise RuntimeError("evidence-map.json must be an object with schemaVersion=1.0.")
    entries = evidence_map.get("features")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("evidence-map.json must contain a non-empty features array.")
    mapped: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("Each evidence-map feature must be an object.")
        name = str(entry.get("name") or entry.get("candidateName") or "").strip()
        if not name:
            raise RuntimeError("Each evidence-map feature requires name.")
        mapped.add(name)
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise RuntimeError(f"Evidence-map feature {name} requires evidence.")
        for item in evidence:
            _validate_reference_evidence_item(item, workspace_path, f"Evidence-map feature {name}")
    missing = sorted(set(declared_feature_names) - mapped)
    if missing:
        raise RuntimeError("evidence-map.json is missing manifest features: " + ", ".join(missing))


def _validate_feature_plan(feature_plan: Any, declared_feature_names: list[str], workspace_path: Path) -> None:
    if not isinstance(feature_plan, dict) or feature_plan.get("schemaVersion") != "1.0":
        raise RuntimeError("feature-plan.json must be an object with schemaVersion=1.0.")
    entries = feature_plan.get("features")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("feature-plan.json must contain a non-empty features array.")
    planned: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("Each feature-plan feature must be an object.")
        name = str(entry.get("name") or "").strip()
        if not name:
            raise RuntimeError("Each feature-plan feature requires name.")
        planned.add(name)
        if not str(entry.get("computation") or "").strip():
            raise RuntimeError(f"Feature-plan feature {name} requires computation.")
        if not str(entry.get("unit") or "").strip():
            raise RuntimeError(f"Feature-plan feature {name} requires unit.")
        if not str(entry.get("controlExpectation") or "").strip():
            raise RuntimeError(f"Feature-plan feature {name} requires controlExpectation.")
        if not isinstance(entry.get("expectedFailureModes"), list) or not entry["expectedFailureModes"]:
            raise RuntimeError(f"Feature-plan feature {name} requires expectedFailureModes.")
        judgments = entry.get("judgmentRules") or entry.get("judgments")
        if not isinstance(judgments, list) or not judgments:
            raise RuntimeError(f"Feature-plan feature {name} requires judgmentRules.")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise RuntimeError(f"Feature-plan feature {name} requires evidence.")
        for item in evidence:
            _validate_reference_evidence_item(item, workspace_path, f"Feature-plan feature {name}")
    missing = sorted(set(declared_feature_names) - planned)
    if missing:
        raise RuntimeError("feature-plan.json is missing manifest features: " + ", ".join(missing))


def _validate_evaluation_report(
    evaluation_report: Any,
    declared_feature_names: list[str],
    workspace_path: Path,
) -> None:
    if not isinstance(evaluation_report, dict) or evaluation_report.get("schemaVersion") != "1.0":
        raise RuntimeError("evaluation-report.json must be an object with schemaVersion=1.0.")
    cases = evaluation_report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RuntimeError("evaluation-report.json must contain a non-empty cases array.")
    try:
        declared_control_count = int(evaluation_report.get("controlCaseCount") or 0)
    except (TypeError, ValueError):
        raise RuntimeError("evaluation-report.json controlCaseCount must be an integer.") from None
    observed_control_count = 0
    evaluated_features: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise RuntimeError(f"evaluation-report.json case {index} must be an object.")
        if _is_real_sample_test_case(workspace_path, case):
            pass
        else:
            source_case = {"source": case.get("source") or case.get("sampleSource")}
            if not _is_real_sample_test_case(workspace_path, source_case):
                raise RuntimeError(f"evaluation-report.json case {index} requires a real sample source.")
        role = str(case.get("role") or case.get("caseRole") or "").casefold()
        if case.get("isControl") is True or role in {"control", "normal", "baseline", "reference", "negative"}:
            observed_control_count += 1
        counts = case.get("featureStatusCounts") or case.get("judgmentDistribution")
        if not isinstance(counts, dict) or not counts:
            raise RuntimeError(f"evaluation-report.json case {index} requires featureStatusCounts.")
        features = case.get("features")
        if isinstance(features, list):
            for feature in features:
                if isinstance(feature, dict) and str(feature.get("name") or "").strip():
                    evaluated_features.add(str(feature["name"]))
    if observed_control_count < 1:
        raise RuntimeError("evaluation-report.json must include at least one control/reference case.")
    if declared_control_count and declared_control_count != observed_control_count:
        raise RuntimeError("evaluation-report.json controlCaseCount does not match observed control/reference cases.")
    missing = sorted(set(declared_feature_names) - evaluated_features)
    if missing:
        raise RuntimeError("evaluation-report.json is missing evaluated features: " + ", ".join(missing))
    summary = evaluation_report.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("evaluation-report.json requires a summary object.")
    if "controlCaseWarnings" not in summary or not isinstance(summary["controlCaseWarnings"], list):
        raise RuntimeError("evaluation-report.json summary requires controlCaseWarnings array.")


def _validate_reference_evidence_item(item: Any, workspace_path: Path, label: str) -> None:
    reference_root = (workspace_path / "references").resolve()
    ref = str(item.get("referencePath", "")) if isinstance(item, dict) else ""
    target = (workspace_path / ref).resolve()
    if not ref.startswith("references/") or reference_root not in target.parents or not target.is_file():
        raise RuntimeError(f"{label} has invalid referencePath: {ref}")
    if not str(item.get("quote", "")).strip() or not (item.get("page") or item.get("section")):
        raise RuntimeError(f"{label} evidence requires quote and page or section.")
    if target.suffix.lower() in {".txt", ".md", ".csv", ".tsv", ".json"}:
        reference_text = " ".join(target.read_text(encoding="utf-8", errors="ignore").split()).casefold()
        quote = " ".join(str(item["quote"]).split()).casefold()
        if quote not in reference_text:
            raise RuntimeError(f"{label} evidence quote was not found in {ref}.")


def _is_real_sample_test_case(workspace_path: Path, case: dict[str, Any]) -> bool:
    source = case.get("source") or case.get("sampleSource")
    if not isinstance(source, dict):
        return False
    source_type = str(source.get("type") or source.get("kind") or "").casefold()
    if source_type not in {"real_sample", "real", "workspace_sample"}:
        return False
    raw_path = str(source.get("path") or source.get("sourcePath") or "").strip()
    if not raw_path:
        return False
    target = (workspace_path / raw_path).resolve()
    try:
        target.relative_to(workspace_path.resolve())
    except ValueError:
        return False
    return target.is_file()


def _validate_deterministic_source(source: str) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise RuntimeError(f"extractor.py is not valid Python: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name.split(".")[0] for alias in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
            blocked = sorted(set(names) - _ALLOWED_IMPORTS)
            if blocked:
                raise RuntimeError("extractor.py imports modules outside the deterministic allowlist: " + ", ".join(blocked))
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
                raise RuntimeError(f"extractor.py calls forbidden function: {node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_ATTRS:
                raise RuntimeError(f"extractor.py calls forbidden API: {node.func.attr}")


def _validate_python_api_manifest(manifest: dict[str, Any]) -> dict[str, str]:
    raw = manifest.get("pythonApi")
    if not isinstance(raw, dict):
        raise RuntimeError("manifest must define pythonApi with file and function for module-style use.")
    file_path = str(raw.get("file") or raw.get("path") or "").strip()
    function = str(raw.get("function") or "").strip()
    if file_path != str(SOURCE_PATH):
        raise RuntimeError(f"manifest.pythonApi.file must be {SOURCE_PATH}.")
    if not function.isidentifier():
        raise RuntimeError("manifest.pythonApi.function must be a valid Python function name.")
    return {"file": file_path, "function": function}


def _load_python_api(workspace_path: Path, python_api: dict[str, str]):
    source_path = workspace_path / python_api["file"]
    module_name = "_harness_reference_feature_extractor"
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load extractor.py as a Python module.")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise RuntimeError(f"extractor.py must be importable without reading stdin or running extraction: {exc}") from exc
    fn = getattr(module, python_api["function"], None)
    if not callable(fn):
        raise RuntimeError(f"extractor.py does not expose callable pythonApi.function {python_api['function']}.")
    return fn


def execute_reference_feature_extractor(workspace_path: Path, input_value: Any) -> dict[str, Any]:
    validate_reference_feature_extractor(workspace_path, run_tests=False)
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0", "TZ": "UTC", "LC_ALL": "C"}
    workspace_python = workspace_path / ".venv" / "bin" / "python"
    completed = subprocess.run(
        [str(workspace_python if workspace_python.exists() else sys.executable), str(workspace_path / SOURCE_PATH)],
        cwd=workspace_path,
        input=json.dumps(input_value, ensure_ascii=False, sort_keys=True),
        text=True,
        capture_output=True,
        timeout=30,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Reference feature extractor failed: {completed.stderr.strip()[:2000]}")
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Reference feature extractor stdout must be one JSON object.") from exc
    manifest = read_json(workspace_path / MANIFEST_PATH)
    _validate_output(output, manifest if isinstance(manifest, dict) else {})
    return output


def execute_reference_feature_module(workspace_path: Path, input_value: Any) -> dict[str, Any]:
    summary = validate_reference_feature_extractor(workspace_path, run_tests=False)
    fn = _load_python_api(workspace_path, summary["pythonApi"])
    try:
        output = fn(input_value)
    except Exception as exc:
        raise RuntimeError(f"Reference feature extractor Python API failed: {exc}") from exc
    manifest = read_json(workspace_path / MANIFEST_PATH)
    _validate_output(output, manifest if isinstance(manifest, dict) else {})
    return output


def _validate_output(output: Any, manifest: dict[str, Any]) -> None:
    if not isinstance(output, dict):
        raise RuntimeError("Extractor output must be one JSON object.")
    schema_version = manifest.get("outputSchema", {}).get("properties", {}).get("schemaVersion", {})
    expected_version = schema_version.get("const") if isinstance(schema_version, dict) else None
    if expected_version is not None and output.get("schemaVersion") != expected_version:
        raise RuntimeError(f"Extractor output must have schemaVersion={expected_version}.")
    required = manifest.get("outputSchema", {}).get("required", [])
    if isinstance(required, list):
        missing_required = [str(key) for key in required if key not in output]
        if missing_required:
            raise RuntimeError("Extractor output is missing required keys: " + ", ".join(missing_required))
    if "features" not in output:
        return
    features = output.get("features")
    if not isinstance(features, list):
        raise RuntimeError("Extractor output.features must be an array when present.")
    if "warnings" in output and not isinstance(output.get("warnings"), list):
        raise RuntimeError("Extractor output.warnings must be an array when present.")
    declared = {str(item.get("name")): item for item in manifest.get("features", []) if isinstance(item, dict)}
    returned_names: set[str] = set()
    for item in features:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            raise RuntimeError("Every output feature requires name.")
        returned_names.add(str(item.get("name")))
        judgment = item.get("judgment")
        if judgment is not None:
            if not isinstance(judgment, dict) or not str(judgment.get("label", "")).strip():
                raise RuntimeError(f"Feature {item.get('name')} requires a judgment with label when judgment is present.")
            if judgment.get("status") not in {"normal", "abnormal", "indeterminate", "not_applicable"}:
                raise RuntimeError(f"Feature {item.get('name')} has invalid judgment.status.")
        output_evidence = item.get("evidence")
        if "evidence" in item and (not isinstance(output_evidence, list) or not output_evidence):
            raise RuntimeError(f"Feature {item.get('name')} evidence must be a non-empty array when present.")
        definition = declared.get(str(item.get("name")))
        if definition is None:
            raise RuntimeError(f"Extractor returned undeclared feature: {item.get('name')}")
        allowed_evidence = {json.dumps(value, ensure_ascii=False, sort_keys=True) for value in definition.get("evidence", [])}
        if isinstance(output_evidence, list):
            for evidence in output_evidence:
                if json.dumps(evidence, ensure_ascii=False, sort_keys=True) not in allowed_evidence:
                    raise RuntimeError(f"Feature {item.get('name')} returned evidence not declared in manifest.")
    missing = sorted(set(declared) - returned_names)
    if missing:
        raise RuntimeError("Extractor output is missing declared features: " + ", ".join(missing))


def inspect_reference_feature_extractor(workspace_path: Path) -> dict[str, Any]:
    summary = validate_reference_feature_extractor(workspace_path, run_tests=False)
    return {
        **summary,
        "manifest": read_json(workspace_path / MANIFEST_PATH),
        "referenceRules": read_json(workspace_path / RULES_PATH),
        "evidenceMap": read_json(workspace_path / EVIDENCE_MAP_PATH),
        "featurePlan": read_json(workspace_path / FEATURE_PLAN_PATH),
        "evaluationReport": read_json(workspace_path / EVALUATION_REPORT_PATH),
        "readme": (workspace_path / README_PATH).read_text(encoding="utf-8"),
        "source": (workspace_path / SOURCE_PATH).read_text(encoding="utf-8"),
    }
