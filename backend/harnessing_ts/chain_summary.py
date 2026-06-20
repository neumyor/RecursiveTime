from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from harnessing_ts.agent.sdk_runner import SdkRunner, SdkRunnerConfig
from harnessing_ts.prompts.compose import (
    build_chain_summary_generate_prompt,
    build_chain_summary_repair_prompt,
    build_chain_summary_repair_system_prompt,
    build_chain_summary_system_prompt,
)
from harnessing_ts.schema import Part
from harnessing_ts.settings.llm import LlmConfig, build_sdk_invocation_config
from harnessing_ts.state.jsonl import read_json, read_jsonl, write_json
from harnessing_ts.state.message_log import MessageLog
from harnessing_ts.state.workspace_store import WorkspaceStore, now_iso


CHAIN_READ_TOOLS = ["Read", "LS", "Glob", "Grep"]
CHAIN_GENERATE_TOOLS = [*CHAIN_READ_TOOLS, "Write"]
CHAIN_REPAIR_TOOLS = ["Read", "Edit"]
CHAIN_DRAFT_PATH = "artifacts/chain-summary.draft.json"
CHAIN_MAX_REPAIR_ATTEMPTS = 6

async def build_chain_summary(
    *,
    workspace_path: Path,
    store: WorkspaceStore,
    llm_config: LlmConfig,
    on_part: Any | None = None,
    on_runner: Any | None = None,
) -> dict[str, Any]:
    sdk_config = build_sdk_invocation_config(llm_config)
    if llm_config.authMode == "manual" and not llm_config.apiKey:
        raise RuntimeError("Chain builder LLM config requires apiKey when authMode=manual.")

    draft_path = workspace_path / CHAIN_DRAFT_PATH
    draft_path.unlink(missing_ok=True)

    runner = SdkRunner(SdkRunnerConfig(
        cwd=workspace_path,
        system_prompt=build_chain_summary_system_prompt(),
        attachment_text=None,
        allowed_tools=CHAIN_GENERATE_TOOLS,
        model=sdk_config.model,
        env=sdk_config.env,
        extra_args=sdk_config.extra_args,
        log=MessageLog(store.chain_summary_log_path),
        on_part=on_part,
    ))
    if on_runner:
        on_runner(runner)
    try:
        prompt = chain_summary_prompt(workspace_path)
        await runner.send_with_user_echo(prompt)
    finally:
        if on_runner:
            on_runner(None)
        await runner.close()

    repair_runner: SdkRunner | None = None
    payload: dict[str, Any] | None = None
    if not draft_path.exists():
        raise RuntimeError(f"Chain builder did not create {CHAIN_DRAFT_PATH}.")
    try:
        for attempt in range(CHAIN_MAX_REPAIR_ATTEMPTS + 1):
            try:
                candidate = read_and_validate_chain_draft(draft_path, workspace_path)
                payload = candidate
                break
            except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                if attempt >= CHAIN_MAX_REPAIR_ATTEMPTS:
                    raise
                if repair_runner is None:
                    repair_runner = SdkRunner(SdkRunnerConfig(
                        cwd=workspace_path,
                        system_prompt=build_chain_summary_repair_system_prompt(),
                        attachment_text=None,
                        allowed_tools=CHAIN_REPAIR_TOOLS,
                        model=sdk_config.model,
                        env=sdk_config.env,
                        extra_args=sdk_config.extra_args,
                        log=MessageLog(store.chain_summary_log_path),
                        on_part=on_part,
                    ))
                if on_runner:
                    on_runner(repair_runner)
                await repair_runner.send_with_user_echo(chain_summary_repair_prompt(str(exc), attempt + 1))
    finally:
        if on_runner:
            on_runner(None)
        if repair_runner is not None:
            await repair_runner.close()

    if payload is None:
        raise RuntimeError("Chain builder did not produce a valid summary after repair.")
    store.write_chain_summary(payload)
    return payload


def chain_summary_prompt(workspace_path: Path) -> str:
    manifest = collect_workspace_manifest(workspace_path)
    return build_chain_summary_generate_prompt(
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        draft_path=CHAIN_DRAFT_PATH,
    )


def chain_summary_repair_prompt(validation_error: str, attempt: int) -> str:
    return build_chain_summary_repair_prompt(
        validation_error=validation_error,
        attempt=attempt,
        max_attempts=CHAIN_MAX_REPAIR_ATTEMPTS,
        draft_path=CHAIN_DRAFT_PATH,
    )


def read_and_validate_chain_draft(draft_path: Path, workspace_path: Path) -> dict[str, Any]:
    if not draft_path.exists():
        raise RuntimeError(f"Chain builder did not create {CHAIN_DRAFT_PATH}.")
    raw = read_json(draft_path)
    if not isinstance(raw, dict):
        raise RuntimeError("Chain summary draft must be a JSON object.")
    candidate = normalize_chain_summary(raw)
    validate_chain_summary(candidate, workspace_path)
    return candidate


def collect_workspace_manifest(workspace_path: Path) -> dict[str, Any]:
    candidates = [
        "logs/main.jsonl",
        "logs/timeline.jsonl",
        "runs/registry.jsonl",
        "user/problem-contract.md",
        "user/data-spec.md",
        "user/solution-plan.md",
        "user/iteration-state.md",
        "reports/final-summary.md",
        "user/final-solution.md",
        "artifacts/knowledge-graph.json",
    ]
    existing = [path for path in candidates if (workspace_path / path).exists()]
    reports = _glob_relative(workspace_path, "reports/iterations/*.md", limit=80)
    run_files = _glob_relative(workspace_path, "runs/iterations/**/*", limit=160)
    tool_files = _glob_relative(workspace_path, "tools/**/README.md", limit=80)
    plots = [
        *(_glob_relative(workspace_path, "plots/**/*", limit=120)),
        *(_glob_relative(workspace_path, "runs/iterations/**/*.png", limit=120)),
        *(_glob_relative(workspace_path, "runs/iterations/**/*.jpg", limit=120)),
        *(_glob_relative(workspace_path, "runs/iterations/**/*.jpeg", limit=120)),
        *(_glob_relative(workspace_path, "runs/iterations/**/*.webp", limit=120)),
        *(_glob_relative(workspace_path, "reports/**/*.png", limit=120)),
    ]
    node_logs = _glob_relative(workspace_path, "logs/nodes/*.jsonl", limit=80)
    references = _glob_relative(workspace_path, "references/**/*", limit=120)
    knowledge_base = _glob_relative(workspace_path, "knowledge_base/**/*", limit=120)
    return {
        "workspace": str(workspace_path),
        "requiredLogs": existing,
        "nodeLogs": node_logs,
        "iterationReports": reports,
        "runFiles": run_files,
        "toolReadmes": tool_files,
        "visualizationCandidates": sorted(set(plots)),
        "referenceFiles": references,
        "knowledgeBaseFiles": knowledge_base,
    }


def parse_chain_summary(parts: list[Part]) -> dict[str, Any]:
    text = ""
    for part in reversed(parts):
        if part.get("role") == "assistant" and isinstance(part.get("text"), str) and part["text"].strip():
            text = part["text"]
            break
    if not text:
        raise RuntimeError("Chain builder did not return a JSON summary.")
    return _loads_json_object(text)


def read_chain_summary(path: Path) -> dict[str, Any]:
    from harnessing_ts.state.jsonl import read_json

    raw = read_json(path)
    return normalize_chain_summary(raw if isinstance(raw, dict) else {})


def normalize_chain_summary(raw: dict[str, Any]) -> dict[str, Any]:
    iterations = raw.get("iterations") if isinstance(raw.get("iterations"), list) else []
    metric_series = raw.get("metricSeries") if isinstance(raw.get("metricSeries"), list) else []
    artifacts = raw.get("artifacts") if isinstance(raw.get("artifacts"), list) else []
    uncertainty = raw.get("uncertainty") if isinstance(raw.get("uncertainty"), list) else []
    return {
        "title": str(raw.get("title") or "思维链总结"),
        "generatedAt": str(raw.get("generatedAt") or now_iso()),
        "overview": str(raw.get("overview") or ""),
        "metricSeries": [_normalize_metric_series(item) for item in metric_series if isinstance(item, dict)],
        "iterations": [_normalize_iteration(item) for item in iterations if isinstance(item, dict)],
        "artifacts": [_normalize_artifact(item) for item in artifacts if isinstance(item, dict)],
        "uncertainty": [str(item) for item in uncertainty if item],
    }


def validate_chain_summary(summary: dict[str, Any], workspace_path: Path) -> None:
    """Reject shallow decision chains instead of persisting a misleading report."""
    iterations = summary.get("iterations") if isinstance(summary.get("iterations"), list) else []
    _require_chinese("title", summary.get("title"))
    _require_chinese("overview", summary.get("overview"))
    for index, warning in enumerate(summary.get("uncertainty", [])):
        _require_chinese(f"uncertainty[{index}]", warning)
    knowledge_available = any([
        (workspace_path / "artifacts" / "knowledge-graph.json").exists(),
        any((workspace_path / "references").glob("**/*")) if (workspace_path / "references").exists() else False,
        any((workspace_path / "knowledge_base").glob("**/*")) if (workspace_path / "knowledge_base").exists() else False,
    ])
    for index, iteration in enumerate(iterations[:-1]):
        decision = iteration.get("nextDecision") if isinstance(iteration.get("nextDecision"), dict) else {}
        iteration_id = iteration.get("iterationId") or index + 1
        if not decision.get("decision") or not decision.get("iterationEvidence"):
            raise RuntimeError(f"Iteration {iteration_id} nextDecision requires decision and iterationEvidence.")
        actions = decision.get("actions") if isinstance(decision.get("actions"), list) else []
        if not actions or any(not all(action.get(key) for key in ("action", "expectedEffect", "validation")) for action in actions):
            raise RuntimeError(f"Iteration {iteration_id} nextDecision requires executable, testable actions.")
        if knowledge_available:
            knowledge = decision.get("domainKnowledge") if isinstance(decision.get("domainKnowledge"), list) else []
            complete = [entry for entry in knowledge if all(entry.get(key) for key in ("knowledge", "sourcePath", "guidance"))]
            if len(complete) < 2:
                raise RuntimeError(f"Iteration {iteration_id} nextDecision requires at least two sourced domain-knowledge links.")
            for knowledge_index, entry in enumerate(complete):
                source_path = workspace_path / entry["sourcePath"]
                try:
                    source_path.resolve().relative_to(workspace_path.resolve())
                except ValueError as exc:
                    raise RuntimeError(f"Iteration {iteration_id} domainKnowledge[{knowledge_index}] sourcePath escapes workspace.") from exc
                if not source_path.is_file():
                    raise RuntimeError(f"Iteration {iteration_id} domainKnowledge[{knowledge_index}] sourcePath does not exist: {entry['sourcePath']}")

    for iteration_index, iteration in enumerate(iterations):
        iteration_id = iteration.get("iterationId") or iteration_index + 1
        for method_index, method in enumerate(iteration.get("methods", [])):
            _require_chinese(f"Iteration {iteration_id} methods[{method_index}].hypothesis", method.get("hypothesis"))
        results = iteration.get("methodResults") or iteration.get("testResults") or []
        for result_index, result in enumerate(results):
            _require_chinese(f"Iteration {iteration_id} results[{result_index}].interpretation", result.get("interpretation"))
        for sample_index, sample in enumerate(iteration.get("sampleInspirations", [])):
            _require_chinese(f"Iteration {iteration_id} sampleInspirations[{sample_index}].interpretation", sample.get("interpretation"))
            _require_chinese(f"Iteration {iteration_id} sampleInspirations[{sample_index}].nextIterationImpact", sample.get("nextIterationImpact"))
        decision = iteration.get("nextDecision") if isinstance(iteration.get("nextDecision"), dict) else {}
        for key in ("decision", "iterationEvidence"):
            if decision.get(key):
                _require_chinese(f"Iteration {iteration_id} nextDecision.{key}", decision[key])
        for knowledge_index, entry in enumerate(decision.get("domainKnowledge", [])):
            _require_chinese(f"Iteration {iteration_id} domainKnowledge[{knowledge_index}].knowledge", entry.get("knowledge"))
            _require_chinese(f"Iteration {iteration_id} domainKnowledge[{knowledge_index}].guidance", entry.get("guidance"))
        for action_index, action in enumerate(decision.get("actions", [])):
            for key in ("action", "expectedEffect", "validation"):
                _require_chinese(f"Iteration {iteration_id} actions[{action_index}].{key}", action.get(key))


def _require_chinese(field: str, value: Any) -> None:
    text = str(value or "").strip()
    if text and not re.search(r"[\u4e00-\u9fff]", text):
        raise RuntimeError(f"{field} must contain Simplified Chinese user-facing text.")


def chain_summary_from_logs(workspace_path: Path) -> dict[str, Any]:
    """Deterministic fallback used by tests and by the UI before the agent runs."""
    timeline = read_jsonl(workspace_path / "logs" / "timeline.jsonl")
    node_events = [event for event in timeline if event.get("type") in {"node_entered", "node_finished"}]
    iterations: list[dict[str, Any]] = []
    for event in node_events:
        if event.get("nodeType") != "iterative-solving" or event.get("type") != "node_finished":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        output_paths = payload.get("outputPaths") if isinstance(payload.get("outputPaths"), list) else []
        iterations.append({
            "iterationId": str(event.get("nodeSessionId") or f"iteration-{len(iterations) + 1}"),
            "methods": [],
            "testResults": [],
            "methodResults": [],
            "sampleInspirations": [],
            "nextDecision": {
                "decision": str(payload.get("nextNode") or payload.get("loopDecision") or ""),
                "iterationEvidence": str(event.get("message") or ""),
                "domainKnowledge": [],
                "actions": [],
            },
            "artifacts": [{"path": str(path), "role": "output"} for path in output_paths],
        })
    return normalize_chain_summary({
        "title": "思维链总结",
        "overview": "Chain builder has not run yet. This placeholder is derived from timeline events.",
        "iterations": iterations,
        "metricSeries": [],
        "artifacts": [],
        "uncertainty": ["Agent-generated summary is not available yet."],
    })


def _normalize_metric_series(item: dict[str, Any]) -> dict[str, Any]:
    values = item.get("values") if isinstance(item.get("values"), list) else []
    normalized_values = []
    for value in values:
        if not isinstance(value, dict):
            continue
        raw = value.get("value")
        try:
            numeric = float(raw)
        except (TypeError, ValueError):
            continue
        normalized_values.append({
            "iteration": str(value.get("iteration") or ""),
            "label": str(value.get("label") or value.get("iteration") or ""),
            "value": numeric,
        })
    return {
        "name": str(item.get("name") or "metric"),
        "unit": str(item.get("unit") or ""),
        "direction": str(item.get("direction") or "neutral"),
        "values": normalized_values,
    }


def _normalize_iteration(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "iterationId": str(item.get("iterationId") or item.get("id") or ""),
        "methods": _normalize_list_of_dicts(item.get("methods"), ("name", "hypothesis", "artifactPath")),
        "testResults": _normalize_list_of_dicts(item.get("testResults"), ("metric", "value", "evidencePath", "interpretation")),
        "methodResults": _normalize_list_of_dicts(item.get("methodResults"), ("methodName", "metric", "value", "evidencePath", "interpretation")),
        "sampleInspirations": _normalize_list_of_dicts(item.get("sampleInspirations"), ("sampleId", "visualizationPath", "interpretation", "nextIterationImpact")),
        "nextDecision": _normalize_next_decision(item),
        "artifacts": [_normalize_artifact(artifact) for artifact in item.get("artifacts", []) if isinstance(artifact, dict)],
    }


def _normalize_next_decision(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("nextDecision") if isinstance(item.get("nextDecision"), dict) else {}
    legacy = str(item.get("nextStep") or "")
    domain_knowledge = raw.get("domainKnowledge") if isinstance(raw.get("domainKnowledge"), list) else []
    actions = raw.get("actions") if isinstance(raw.get("actions"), list) else []
    return {
        "decision": str(raw.get("decision") or legacy),
        "iterationEvidence": str(raw.get("iterationEvidence") or ""),
        "domainKnowledge": [
            {key: str(entry.get(key) or "") for key in ("knowledge", "sourcePath", "guidance")}
            for entry in domain_knowledge if isinstance(entry, dict)
        ],
        "actions": [
            {key: str(entry.get(key) or "") for key in ("action", "expectedEffect", "validation")}
            for entry in actions if isinstance(entry, dict)
        ],
        "legacy": bool(legacy and not raw),
    }


def _normalize_artifact(item: dict[str, Any]) -> dict[str, str]:
    return {"path": str(item.get("path") or ""), "role": str(item.get("role") or "")}


def _normalize_list_of_dicts(value: Any, keys: tuple[str, ...]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append({key: str(item.get(key) or "") for key in keys})
    return out


def _loads_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise RuntimeError("Chain builder output must be a JSON object.")
    return value


def _glob_relative(root: Path, pattern: str, limit: int) -> list[str]:
    out: list[str] = []
    for path in sorted(root.glob(pattern)):
        if len(out) >= limit:
            break
        if path.is_file():
            out.append(str(path.relative_to(root)))
    return out
