from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from harnessing_ts.agent.sdk_runner import SdkRunner, SdkRunnerConfig
from harnessing_ts.schema import Part
from harnessing_ts.settings.llm import LlmConfig, build_sdk_invocation_config
from harnessing_ts.state.jsonl import read_jsonl, write_json
from harnessing_ts.state.message_log import MessageLog
from harnessing_ts.state.workspace_store import WorkspaceStore, now_iso


CHAIN_ALLOWED_TOOLS = ["Read", "LS", "Glob", "Grep"]

CHAIN_SYSTEM_PROMPT = """你是 HarnessingTS 的独立 chain builder agent。

你的职责是读取当前 runtime workspace 的 logs、runs、reports、tools 和 user 工件，生成一份可审计的“思维链总结”。
这里的“思维链”只能指可观察的决策链和证据链：主会话或 node agent 在日志和报告中明确提出了什么方法、执行了什么测试、产生了什么指标、从哪些 bad case 或样本可视化获得了下一轮启发。不要编造隐藏推理，不要输出模型私有思考过程。

必须输出合法 JSON，不能使用 Markdown fence。JSON schema:
{
  "title": "string",
  "generatedAt": "ISO timestamp or empty",
  "overview": "string",
  "metricSeries": [
    {
      "name": "metric name",
      "unit": "optional unit",
      "direction": "higher|lower|neutral",
      "values": [{"iteration": "iteration number or id", "label": "best candidate/method label for this iteration", "value": number}]
    }
  ],
  "iterations": [
    {
      "iterationId": "string",
      "summary": "string",
      "methods": [{"name": "string", "hypothesis": "string", "artifactPath": "optional path"}],
      "testResults": [{"metric": "string", "value": "string", "evidencePath": "optional path", "interpretation": "string"}],
      "methodResults": [
        {
          "methodName": "must match the paired methods[].name",
          "metric": "primary/core metric for this method",
          "value": "string",
          "evidencePath": "optional path",
          "interpretation": "string"
        }
      ],
      "sampleInspirations": [
        {
          "sampleId": "string",
          "visualizationPath": "workspace relative image path if available",
          "interpretation": "string",
          "nextIterationImpact": "string"
        }
      ],
      "nextStep": "string"
    }
  ],
  "artifacts": [{"path": "workspace relative path", "role": "string"}],
  "uncertainty": ["string"]
}

要求：
- metricSeries 必须尽量从 iteration summaries、runs registry、metrics 文件中抽取多个“指标 x iterations”的序列。每个 metric 的每个 iteration 只能保留该 iteration 的最佳结果；横轴语义必须是 iteration 编号或 id，不要把 candidate 名称当作横轴。
- overview 只写核心决策链摘要，不要把日志读取限制、warning、缺失文件清单写进 overview。此类信息放入 uncertainty，且每条 uncertainty 必须简短。
- 每个 iteration 的 methods 和 methodResults 必须严格一一对应：顺序相同、数量相同，methodResults[i] 解释 methods[i] 的测试结果和核心指标。如果只能产出旧字段 testResults，也必须保证 testResults 的顺序和 methods 一致。
- sampleInspirations 必须优先使用 case review 中的样本、可视化路径和解读；没有图片路径时 visualizationPath 留空并说明缺失。
- 所有 path 必须是 workspace 相对路径。
- 如果日志不足，仍输出 JSON，并把缺口写入 uncertainty。
"""


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

    runner = SdkRunner(SdkRunnerConfig(
        cwd=workspace_path,
        system_prompt=CHAIN_SYSTEM_PROMPT,
        attachment_text=None,
        allowed_tools=CHAIN_ALLOWED_TOOLS,
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
        parts = await runner.send_with_user_echo(prompt)
    finally:
        if on_runner:
            on_runner(None)
        await runner.close()

    payload = parse_chain_summary(parts)
    payload = normalize_chain_summary(payload)
    store.write_chain_summary(payload)
    return payload


def chain_summary_prompt(workspace_path: Path) -> str:
    manifest = collect_workspace_manifest(workspace_path)
    return "\n".join([
        "请生成 HarnessingTS 当前 workspace 的思维链总结。",
        "",
        "请读取以下 runtime workspace 日志和工件，必要时用 Glob/Grep/Read 深入查看相关文件：",
        json.dumps(manifest, ensure_ascii=False, indent=2),
        "",
        "重点回答：",
        "1. 每个 iteration 中提出了哪些方法或候选，保留/放弃原因是什么。",
        "2. 每轮测试结果如何，哪些指标提升或退化。",
        "3. 哪些样本、bad case 或可视化启发了下一轮 iteration。",
        "4. 最终目标是如何通过一轮轮外显决策和证据实现的。",
        "",
        "输出约束：",
        "- metricSeries.values 的 iteration 字段必须是 iteration 编号/id；label 只能用于备注本轮最佳候选。",
        "- 对每个 iteration，methods 与 methodResults 必须按 candidate/method 一一配对，数量和顺序一致。",
        "- 不要在 overview 中写 warning 列表；日志缺口只放到 uncertainty，最多 6 条，每条一句。",
        "",
        "只输出符合 system prompt schema 的 JSON。",
    ])


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
    return {
        "workspace": str(workspace_path),
        "requiredLogs": existing,
        "nodeLogs": node_logs,
        "iterationReports": reports,
        "runFiles": run_files,
        "toolReadmes": tool_files,
        "visualizationCandidates": sorted(set(plots)),
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
            "summary": str(event.get("message") or ""),
            "methods": [],
            "testResults": [],
            "methodResults": [],
            "sampleInspirations": [],
            "nextStep": str(payload.get("nextNode") or payload.get("loopDecision") or ""),
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
        "summary": str(item.get("summary") or ""),
        "methods": _normalize_list_of_dicts(item.get("methods"), ("name", "hypothesis", "artifactPath")),
        "testResults": _normalize_list_of_dicts(item.get("testResults"), ("metric", "value", "evidencePath", "interpretation")),
        "methodResults": _normalize_list_of_dicts(item.get("methodResults"), ("methodName", "metric", "value", "evidencePath", "interpretation")),
        "sampleInspirations": _normalize_list_of_dicts(item.get("sampleInspirations"), ("sampleId", "visualizationPath", "interpretation", "nextIterationImpact")),
        "nextStep": str(item.get("nextStep") or ""),
        "artifacts": [_normalize_artifact(artifact) for artifact in item.get("artifacts", []) if isinstance(artifact, dict)],
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
