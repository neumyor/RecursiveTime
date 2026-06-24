from __future__ import annotations

import ast
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
    required = [MANIFEST_PATH, SOURCE_PATH, RULES_PATH, README_PATH, TEST_CASES_PATH]
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
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != "1.0":
        raise RuntimeError("manifest.json must be an object with schemaVersion=1.0.")
    if manifest.get("entrypoint") != str(SOURCE_PATH):
        raise RuntimeError(f"manifest entrypoint must be {SOURCE_PATH}.")
    if not isinstance(manifest.get("inputSchema"), dict) or not isinstance(manifest.get("outputSchema"), dict):
        raise RuntimeError("manifest must define inputSchema and outputSchema objects.")
    output_required = manifest["outputSchema"].get("required")
    if manifest["outputSchema"].get("type") != "object" or not {"schemaVersion", "features", "warnings"}.issubset(set(output_required or [])):
        raise RuntimeError("manifest.outputSchema must require schemaVersion, features, and warnings.")
    features = manifest.get("features")
    if not isinstance(features, list) or not features:
        raise RuntimeError("manifest.features must contain at least one feature definition.")
    reference_root = (workspace_path / "references").resolve()
    for feature in features:
        if not isinstance(feature, dict) or not str(feature.get("name", "")).strip():
            raise RuntimeError("Each manifest feature requires a non-empty name.")
        evidence = feature.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise RuntimeError(f"Feature {feature.get('name')} requires reference evidence.")
        for item in evidence:
            ref = str(item.get("referencePath", "")) if isinstance(item, dict) else ""
            target = (workspace_path / ref).resolve()
            if not ref.startswith("references/") or reference_root not in target.parents or not target.is_file():
                raise RuntimeError(f"Feature {feature.get('name')} has invalid referencePath: {ref}")
            if not str(item.get("quote", "")).strip() or not (item.get("page") or item.get("section")):
                raise RuntimeError(f"Feature {feature.get('name')} evidence requires quote and page or section.")
            if target.suffix.lower() in {".txt", ".md", ".csv", ".tsv", ".json"}:
                reference_text = " ".join(target.read_text(encoding="utf-8", errors="ignore").split()).casefold()
                quote = " ".join(str(item["quote"]).split()).casefold()
                if quote not in reference_text:
                    raise RuntimeError(f"Feature {feature.get('name')} evidence quote was not found in {ref}.")
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

    source = (workspace_path / SOURCE_PATH).read_text(encoding="utf-8")
    _validate_deterministic_source(source)
    result = {
        "ready": True,
        "toolDir": str(TOOL_DIR),
        "manifestPath": str(MANIFEST_PATH),
        "sourcePath": str(SOURCE_PATH),
        "readmePath": str(README_PATH),
        "featureCount": len(features),
        "features": [str(item.get("name")) for item in features],
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
            checked += 1
        result["testsPassed"] = checked
    return result


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


def _validate_output(output: Any, manifest: dict[str, Any]) -> None:
    if not isinstance(output, dict) or output.get("schemaVersion") != "1.0":
        raise RuntimeError("Extractor output must be an object with schemaVersion=1.0.")
    features = output.get("features")
    if not isinstance(features, list):
        raise RuntimeError("Extractor output.features must be an array.")
    declared = {str(item.get("name")): item for item in manifest.get("features", []) if isinstance(item, dict)}
    for item in features:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip() or "value" not in item:
            raise RuntimeError("Every output feature requires name and value.")
        judgment = item.get("judgment")
        if not isinstance(judgment, dict) or not str(judgment.get("label", "")).strip():
            raise RuntimeError(f"Feature {item.get('name')} requires a judgment with label.")
        if judgment.get("status") not in {"normal", "abnormal", "indeterminate", "not_applicable"}:
            raise RuntimeError(f"Feature {item.get('name')} has invalid judgment.status.")
        if not isinstance(item.get("evidence"), list) or not item["evidence"]:
            raise RuntimeError(f"Feature {item.get('name')} requires reference evidence in output.")
        definition = declared.get(str(item.get("name")))
        if definition is None:
            raise RuntimeError(f"Extractor returned undeclared feature: {item.get('name')}")
        allowed_evidence = {json.dumps(value, ensure_ascii=False, sort_keys=True) for value in definition.get("evidence", [])}
        for evidence in item["evidence"]:
            if json.dumps(evidence, ensure_ascii=False, sort_keys=True) not in allowed_evidence:
                raise RuntimeError(f"Feature {item.get('name')} returned evidence not declared in manifest.")


def inspect_reference_feature_extractor(workspace_path: Path) -> dict[str, Any]:
    summary = validate_reference_feature_extractor(workspace_path, run_tests=False)
    return {
        **summary,
        "manifest": read_json(workspace_path / MANIFEST_PATH),
        "referenceRules": read_json(workspace_path / RULES_PATH),
        "readme": (workspace_path / README_PATH).read_text(encoding="utf-8"),
        "source": (workspace_path / SOURCE_PATH).read_text(encoding="utf-8"),
    }
