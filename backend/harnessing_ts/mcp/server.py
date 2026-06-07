from __future__ import annotations

import json
import inspect
from typing import Any, Callable

from harnessing_ts.schema import NODE_TYPES


def text_result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def create_harness_mcp_server(
    *,
    session_role: str,
    enter_node: Callable[[dict[str, Any]], Any] | None = None,
    finish_node: Callable[[dict[str, Any]], Any] | None = None,
    record_artifact: Callable[[dict[str, Any]], Any] | None = None,
    record_run: Callable[[dict[str, Any]], Any] | None = None,
) -> Any:
    try:
        from claude_code_sdk import create_sdk_mcp_server, tool
    except Exception:
        return None

    tools: list[Any] = []

    if session_role == "main" and enter_node:
        @tool(
            name="enter_node",
            description="Request entry into a time-series tool-use harness node. The harness either auto-allows it or parks it for human approval according to TS_HARNESS_CONTROL_MODE.",
            input_schema={
                "type": "object",
                "properties": {
                    "nodeType": {"type": "string", "enum": list(NODE_TYPES)},
                    "rationale": {"type": "string"},
                    "inputSummary": {"type": "string"},
                },
                "required": ["nodeType", "rationale"],
            },
        )
        async def _enter_node(args: dict[str, Any]) -> dict[str, Any]:
            return text_result(await _maybe_await(enter_node(args)))

        tools.append(_enter_node)

    if session_role == "node" and finish_node:
        @tool(
            name="finish_node",
            description="Request completion of the active node. The harness either auto-allows it or parks it for human approval according to TS_HARNESS_CONTROL_MODE.",
            input_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "summary": {"type": "string"},
                    "goalMet": {"type": "boolean"},
                    "nextNode": {
                        "type": "string",
                        "enum": [*list(NODE_TYPES), "none"],
                        "description": "Structured node routing decision. For iterative-solving, use iterative-solving to continue or final-summary to exit.",
                    },
                    "loopDecision": {
                        "type": "string",
                        "enum": ["continue", "exit", "none"],
                        "description": "Structured loop decision for iterative-solving. Use continue for another iteration, exit for final-summary.",
                    },
                    "outputPaths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["success", "summary"],
            },
        )
        async def _finish_node(args: dict[str, Any]) -> dict[str, Any]:
            return text_result(await _maybe_await(finish_node(args)))

        tools.append(_finish_node)

    if session_role == "node" and record_artifact:
        @tool(
            name="record_artifact",
            description="Record a produced artifact path in the harness timeline.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}, "summary": {"type": "string"}},
                "required": ["path"],
            },
        )
        async def _record_artifact(args: dict[str, Any]) -> dict[str, Any]:
            return text_result(await _maybe_await(record_artifact(args)))

        tools.append(_record_artifact)

    if session_role == "node" and record_run:
        @tool(
            name="record_run",
            description="Record a tool-guided solving run in runs/registry.jsonl.",
            input_schema={
                "type": "object",
                "properties": {
                    "runId": {"type": "string"},
                    "status": {"type": "string", "enum": ["running", "completed", "failed"]},
                    "startedAt": {"type": "string"},
                    "finishedAt": {"type": "string"},
                    "artifactPaths": {"type": "array", "items": {"type": "string"}},
                    "summary": {"type": "string"},
                    "metrics": {"type": "object"},
                },
                "required": ["runId", "status", "startedAt", "artifactPaths"],
            },
        )
        async def _record_run(args: dict[str, Any]) -> dict[str, Any]:
            return text_result(await _maybe_await(record_run(args)))

        tools.append(_record_run)

    return create_sdk_mcp_server(name="ts_harness", version="0.1.0", tools=tools)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value
