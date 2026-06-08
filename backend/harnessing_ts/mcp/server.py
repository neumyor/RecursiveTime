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
    query_knowledge: Callable[[dict[str, Any]], Any] | None = None,
    finish_node: Callable[[dict[str, Any]], Any] | None = None,
    record_artifact: Callable[[dict[str, Any]], Any] | None = None,
    record_run: Callable[[dict[str, Any]], Any] | None = None,
    get_runtime_settings: Callable[[], Any] | None = None,
    knowledge_base_tools: dict[str, Callable[[dict[str, Any]], Any]] | None = None,
) -> Any:
    try:
        from claude_code_sdk import create_sdk_mcp_server, tool
    except Exception:
        return None

    tools: list[Any] = []

    if session_role == "knowledge_builder" and knowledge_base_tools:
        _add_knowledge_base_tools(tools, tool, knowledge_base_tools)

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

    if session_role == "main" and query_knowledge:
        @tool(
            name="query_knowledge",
            description="Ask the independent knowledge reasoning agent a natural-language domain question. Use this to retrieve evidence-backed domain knowledge from the reference knowledge base.",
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "domain": {"type": "string"},
                    "context": {"type": "object"},
                    "observations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question"],
            },
        )
        async def _query_knowledge(args: dict[str, Any]) -> dict[str, Any]:
            return text_result(await _maybe_await(query_knowledge(args)))

        tools.append(_query_knowledge)

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

    if session_role == "node" and get_runtime_settings:
        @tool(
            name="get_runtime_settings",
            description="Read live harness runtime parameters. Iterative-solving must call this before proposing candidate solutions so UI changes to iterativeCandidateCount take effect.",
            input_schema={
                "type": "object",
                "properties": {},
            },
        )
        async def _get_runtime_settings(args: dict[str, Any]) -> dict[str, Any]:
            return text_result(await _maybe_await(get_runtime_settings()))

        tools.append(_get_runtime_settings)

    return create_sdk_mcp_server(name="ts_harness", version="0.1.0", tools=tools)


def _add_knowledge_base_tools(tools: list[Any], tool: Any, callbacks: dict[str, Callable[[dict[str, Any]], Any]]) -> None:
    def callback(name: str) -> Callable[[dict[str, Any]], Any]:
        return callbacks[name]

    @tool(
        name="scan_references",
        description="Scan workspace references, compute hashes, and return new/changed references plus compact unchanged reference briefs.",
        input_schema={"type": "object", "properties": {"include_processed": {"type": "boolean"}}},
    )
    async def _scan_references(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("scan_references")(args)))

    @tool(
        name="extract_reference_text",
        description="Extract deterministic text from a reference. For PDFs this uses pdftotext page-by-page and writes a cache under knowledge_base/cache/reference_text. Use this before SDK Read when building evidence quoted_fragments.",
        input_schema={
            "type": "object",
            "properties": {
                "reference_id": {"type": "string"},
                "path": {"type": "string"},
                "pages": {"type": "string", "description": "Optional page selection like 1,3-5."},
                "max_chars_per_page": {"type": "integer"},
            },
        },
    )
    async def _extract_reference_text(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("extract_reference_text")(args)))

    @tool(
        name="update_reference_brief",
        description="Update the compact title and brief for a processed reference.",
        input_schema={
            "type": "object",
            "properties": {
                "reference_id": {"type": "string"},
                "title": {"type": "string"},
                "brief": {"type": "string"},
            },
            "required": ["reference_id", "brief"],
        },
    )
    async def _update_reference_brief(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("update_reference_brief")(args)))

    @tool(
        name="add_evidence",
        description="Add an evidence record. The tool assigns E-xxxxx, normalizes reference_file, JSON-serializes quoted_fragments, and writes evidence.csv.",
        input_schema={
            "type": "object",
            "properties": {
                "reference_file": {"type": "string"},
                "page": {"type": "string"},
                "section": {"type": "string"},
                "quoted_fragments": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["reference_file", "quoted_fragments"],
        },
    )
    async def _add_evidence(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("add_evidence")(args)))

    @tool(
        name="add_knowledge",
        description="Add a knowledge record supported by evidence. The tool assigns K-xxxxx and marks it pending_graph.",
        input_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "description": {"type": "string"},
                "summary": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["topic", "description", "evidence_ids"],
        },
    )
    async def _add_knowledge(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("add_knowledge")(args)))

    @tool(
        name="list_pending_knowledge",
        description="Return compact pending knowledge records that still need class/relation graph processing.",
        input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
    )
    async def _list_pending_knowledge(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("list_pending_knowledge")(args)))

    @tool(
        name="get_knowledge",
        description="Read one knowledge record. Compact detail avoids long context; full includes description and notes.",
        input_schema={
            "type": "object",
            "properties": {
                "knowledge_id": {"type": "string"},
                "detail": {"type": "string", "enum": ["compact", "full"]},
            },
            "required": ["knowledge_id"],
        },
    )
    async def _get_knowledge(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("get_knowledge")(args)))

    @tool(
        name="search_classes",
        description="Search existing classes by normalized label, aliases, and keywords before deciding whether to reuse or create a class.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
            "required": ["query"],
        },
    )
    async def _search_classes(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("search_classes")(args)))

    @tool(
        name="upsert_class",
        description="Create or merge a class. The tool normalizes label, assigns/reuses C-xxxxx, merges evidence and source knowledge, and backfills knowledge.class_ids.",
        input_schema={
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "description_addition": {"type": "string"},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "source_knowledge_ids": {"type": "array", "items": {"type": "string"}},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["label", "description_addition", "source_knowledge_ids"],
        },
    )
    async def _upsert_class(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("upsert_class")(args)))

    @tool(
        name="search_relations",
        description="Search existing relations by source class, target class, and optional relation type before upserting.",
        input_schema={
            "type": "object",
            "properties": {
                "source_class_id": {"type": "string"},
                "target_class_id": {"type": "string"},
                "relation_type": {"type": "string"},
            },
        },
    )
    async def _search_relations(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("search_relations")(args)))

    @tool(
        name="upsert_relation",
        description="Create or merge a relation. The tool validates class ids, normalizes relation_type, merges evidence/source knowledge, and backfills knowledge.relation_ids.",
        input_schema={
            "type": "object",
            "properties": {
                "source_class_id": {"type": "string"},
                "relation_type": {"type": "string"},
                "target_class_id": {"type": "string"},
                "description_addition": {"type": "string"},
                "source_knowledge_ids": {"type": "array", "items": {"type": "string"}},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["source_class_id", "relation_type", "target_class_id", "description_addition", "source_knowledge_ids"],
        },
    )
    async def _upsert_relation(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("upsert_relation")(args)))

    @tool(
        name="validate_knowledge_base",
        description="Validate CSV schema, references, IDs, graph endpoints, and evidence coverage. Returns errors and warnings without writing manifest.",
        input_schema={"type": "object", "properties": {}},
    )
    async def _validate_knowledge_base(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("validate_knowledge_base")(args)))

    @tool(
        name="finalize_knowledge_base",
        description="Finalize the knowledge base: inherit evidence, validate, write manifest, and update indexes.",
        input_schema={"type": "object", "properties": {}},
    )
    async def _finalize_knowledge_base(args: dict[str, Any]) -> dict[str, Any]:
        return text_result(await _maybe_await(callback("finalize_knowledge_base")(args)))

    tools.extend([
        _scan_references,
        _extract_reference_text,
        _update_reference_brief,
        _add_evidence,
        _add_knowledge,
        _list_pending_knowledge,
        _get_knowledge,
        _search_classes,
        _upsert_class,
        _search_relations,
        _upsert_relation,
        _validate_knowledge_base,
        _finalize_knowledge_base,
    ])


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value
