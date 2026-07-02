from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

from harnessing_ts.agent.sdk_runner import SdkRunner, SdkRunnerConfig
from harnessing_ts.knowledge_prompts import REASONER_SYSTEM_PROMPT, REFERENCE_REASONER_SYSTEM_PROMPT, builder_system_prompt, knowledge_graph_prompt
from harnessing_ts.schema import Part
from harnessing_ts.settings.llm import LlmConfig, build_sdk_invocation_config
from harnessing_ts.state.message_log import MessageLog
from harnessing_ts.state.workspace_store import WorkspaceStore, now_iso


KG_TOOL_NAMES = [
    "scan_references",
    "extract_reference_text",
    "update_reference_brief",
    "add_evidence",
    "add_knowledge",
    "list_pending_knowledge",
    "get_knowledge",
    "search_classes",
    "upsert_class",
    "search_relations",
    "upsert_relation",
    "validate_knowledge_base",
    "finalize_knowledge_base",
]
KG_ALLOWED_TOOLS = ["Read", "LS", "Glob", "Grep", *[f"mcp__ts_harness__{name}" for name in KG_TOOL_NAMES]]
REFERENCE_FIELDS = ["reference_id", "path", "sha256", "title", "brief", "status", "updated_at"]
EVIDENCE_FIELDS = ["evidence_id", "reference_file", "page", "section", "quoted_fragments", "notes"]
KNOWLEDGE_FIELDS = ["knowledge_id", "topic", "description", "summary", "evidence_ids", "class_ids", "relation_ids", "status", "notes"]
CLASS_FIELDS = ["class_id", "label", "normalized_label", "concept_level", "concept_type", "description", "source_knowledge_ids", "evidence_ids", "aliases"]
RELATION_FIELDS = ["relation_id", "source_class_id", "relation_type", "target_class_id", "relation_depth", "description", "source_knowledge_ids", "evidence_ids"]
CONCEPT_TYPES = {
    "entity",
    "abnormality_pattern",
    "signal_feature",
    "waveform",
    "interval",
    "threshold",
    "condition",
    "confounder",
    "task",
    "dataset",
    "method",
    "evidence_source",
    "mechanism",
    "next_check",
}

async def build_knowledge_graph(
    *,
    workspace_path: Path,
    store: WorkspaceStore,
    llm_config: LlmConfig,
    trigger: str,
    uploaded_paths: list[str] | None = None,
    on_part: Any | None = None,
    on_runner: Any | None = None,
    on_change: Any | None = None,
) -> list[Part]:
    ensure_knowledge_base_layout(store.root)
    _ensure_domain_brief(store.root)
    extraction_depth = _graph_extraction_depth(store.root)
    sdk_config = build_sdk_invocation_config(llm_config)
    if llm_config.authMode == "manual" and not llm_config.apiKey:
        raise RuntimeError("Knowledge builder LLM config requires apiKey when authMode=manual.")
    from harnessing_ts.mcp.server import create_harness_mcp_server

    mcp_server = create_harness_mcp_server(
        session_role="knowledge_builder",
        knowledge_base_tools=build_knowledge_base_tool_callbacks(store.root, on_change=on_change),
    )
    runner = SdkRunner(SdkRunnerConfig(
        cwd=workspace_path,
        system_prompt=builder_system_prompt(extraction_depth),
        attachment_text=None,
        allowed_tools=KG_ALLOWED_TOOLS,
        model=sdk_config.model,
        env=sdk_config.env,
        extra_args=sdk_config.extra_args,
        log=MessageLog(store.knowledge_graph_log_path),
        mcp_server=mcp_server,
        on_part=on_part,
    ))
    if on_runner:
        on_runner(runner)
    try:
        parts = await runner.send_with_user_echo(knowledge_graph_prompt(trigger, uploaded_paths))
    finally:
        if on_runner:
            on_runner(None)
        await runner.close()
    finalize_knowledge_base(store.root)
    if on_change:
        on_change()
    return parts


async def answer_knowledge_query(
    *,
    workspace_path: Path,
    store: WorkspaceStore,
    llm_config: LlmConfig,
    question: str,
    domain: str | None = None,
    context: dict[str, Any] | None = None,
    observations: list[str] | None = None,
    include_evidence: bool = False,
) -> dict[str, Any]:
    ensure_knowledge_base_layout(store.root)
    retrieval = retrieve_knowledge_context(store.root, question, top_k=6)
    sdk_config = build_sdk_invocation_config(llm_config)
    if llm_config.authMode == "manual" and not llm_config.apiKey:
        raise RuntimeError("Knowledge reasoning LLM config requires apiKey when authMode=manual.")
    prompt = "\n".join([
        "请根据以下检索上下文回答问题。",
        "",
        f"Domain: {domain or 'default'}",
        f"Question: {question}",
        f"Context: {json.dumps(context or {}, ensure_ascii=False)}",
        f"Observations: {json.dumps(observations or [], ensure_ascii=False)}",
        f"Include evidence details: {json.dumps(include_evidence)}",
        "",
        "Retrieved Knowledge:",
        _format_retrieved_items(retrieval["knowledge_notes"]),
        "",
        "Retrieved Evidence:",
        _format_retrieved_items(retrieval["evidence_notes"]),
        "",
        "Retrieved Relations:",
        json.dumps(retrieval["graph_edges"], ensure_ascii=False, indent=2),
        "",
        "默认输出简洁、面向主会话可直接使用的答案。只有 Include evidence details 为 true 时，才输出 supporting_evidence、related_graph_edges 或 retrieval 细节；否则这些字段应省略或为空数组。",
        "只输出合法 JSON，不要输出 Markdown fence。",
    ])
    runner = SdkRunner(SdkRunnerConfig(
        cwd=workspace_path,
        system_prompt=REASONER_SYSTEM_PROMPT,
        attachment_text=None,
        allowed_tools=[],
        model=sdk_config.model,
        env=sdk_config.env,
        extra_args=sdk_config.extra_args,
        log=MessageLog(store.knowledge_reasoning_log_path),
    ))
    try:
        parts = await runner.send_with_user_echo(prompt)
    finally:
        await runner.close()
    answer_text = _last_assistant_text(parts)
    parsed = _parse_json_answer(answer_text)
    if include_evidence:
        parsed.setdefault("retrieval", retrieval)
    else:
        parsed = _compact_knowledge_query_answer(parsed)
    return parsed


async def answer_reference_query(
    *,
    workspace_path: Path,
    store: WorkspaceStore,
    llm_config: LlmConfig,
    question: str,
    domain: str | None = None,
    context: dict[str, Any] | None = None,
    observations: list[str] | None = None,
    include_evidence: bool = False,
) -> dict[str, Any]:
    sdk_config = build_sdk_invocation_config(llm_config)
    if llm_config.authMode == "manual" and not llm_config.apiKey:
        raise RuntimeError("Reference reasoning LLM config requires apiKey when authMode=manual.")
    prompt = "\n".join([
        "请直接根据当前 workspace 的 `references/**` 原文回答问题，不要使用 knowledge graph、knowledge_base CSV、class、relation 或 graph edges。",
        "可读取 `user/problem-contract.md`、`user/data-spec.md` 和 references 下的文本/PDF/DOCX 文本衍生文件来确定任务边界。",
        "若 reference 证据不足，必须明确 uncertainty，不要补充无来源规则。",
        "",
        f"Domain: {domain or 'default'}",
        f"Question: {question}",
        f"Context: {json.dumps(context or {}, ensure_ascii=False)}",
        f"Observations: {json.dumps(observations or [], ensure_ascii=False)}",
        f"Include evidence details: {json.dumps(include_evidence)}",
        "",
        "输出 JSON：",
        "{",
        '  "answer": "自然语言回答",',
        '  "candidate_targets": ["候选概念或异常模式"],',
        '  "supporting_knowledge": ["reference 文件或章节摘要"],',
        '  "supporting_evidence": [],',
        '  "related_graph_edges": [],',
        '  "recommended_next_checks": ["..."],',
        '  "uncertainty": "..."',
        "}",
        "",
        "只有 Include evidence details 为 true 时，supporting_evidence 才应包含必要的短引用、文件路径、页码或章节；否则保持空数组或省略。",
        "只输出合法 JSON，不要输出 Markdown fence。",
    ])
    runner = SdkRunner(SdkRunnerConfig(
        cwd=workspace_path,
        system_prompt=REFERENCE_REASONER_SYSTEM_PROMPT,
        attachment_text=None,
        allowed_tools=["Read", "LS", "Glob", "Grep"],
        model=sdk_config.model,
        env=sdk_config.env,
        extra_args=sdk_config.extra_args,
        log=MessageLog(store.knowledge_reasoning_log_path),
    ))
    try:
        parts = await runner.send_with_user_echo(prompt)
    finally:
        await runner.close()
    parsed = _parse_json_answer(_last_assistant_text(parts))
    if include_evidence:
        parsed.setdefault("retrieval", {"source": "references"})
    else:
        parsed = _compact_knowledge_query_answer(parsed)
    parsed["knowledge_source"] = "references"
    return parsed


def ensure_knowledge_base_layout(root: Path) -> None:
    for rel in (
        "knowledge_base",
        "knowledge_base/tables",
        "knowledge_base/indexes",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    _ensure_csv_header(root / "knowledge_base" / "tables" / "references.csv", REFERENCE_FIELDS)
    _ensure_csv_header(root / "knowledge_base" / "tables" / "evidence.csv", EVIDENCE_FIELDS)
    _ensure_csv_header(root / "knowledge_base" / "tables" / "knowledge.csv", KNOWLEDGE_FIELDS)
    _ensure_csv_header(root / "knowledge_base" / "tables" / "classes.csv", CLASS_FIELDS)
    _ensure_csv_header(root / "knowledge_base" / "tables" / "relations.csv", RELATION_FIELDS)


def build_knowledge_base_tool_callbacks(root: Path, on_change: Any | None = None) -> dict[str, Any]:
    callbacks = {
        "scan_references": lambda args: scan_references(root, bool(args.get("include_processed", False))),
        "extract_reference_text": lambda args: extract_reference_text(root, args),
        "update_reference_brief": lambda args: update_reference_brief(
            root,
            str(args.get("reference_id", "")),
            str(args.get("title", "")),
            str(args.get("brief", "")),
        ),
        "add_evidence": lambda args: add_evidence(root, args),
        "add_knowledge": lambda args: add_knowledge(root, args),
        "list_pending_knowledge": lambda args: list_pending_knowledge(root, int(args.get("limit") or 10)),
        "get_knowledge": lambda args: get_knowledge(root, str(args.get("knowledge_id", "")), str(args.get("detail") or "compact")),
        "search_classes": lambda args: search_classes(root, str(args.get("query", "")), int(args.get("top_k") or 5)),
        "upsert_class": lambda args: upsert_class(root, args),
        "search_relations": lambda args: search_relations(
            root,
            str(args.get("source_class_id", "")),
            str(args.get("target_class_id", "")),
            str(args.get("relation_type", "")),
        ),
        "upsert_relation": lambda args: upsert_relation(root, args),
        "validate_knowledge_base": lambda args: validate_knowledge_base_report(root),
        "finalize_knowledge_base": lambda args: finalize_knowledge_base(root),
    }
    mutating_tools = {
        "scan_references",
        "update_reference_brief",
        "add_evidence",
        "add_knowledge",
        "upsert_class",
        "upsert_relation",
        "finalize_knowledge_base",
    }
    if on_change:
        for name in mutating_tools:
            callback = callbacks[name]

            def notify_after(args: dict[str, Any], callback: Any = callback) -> Any:
                result = callback(args)
                on_change()
                return result

            callbacks[name] = notify_after
    return callbacks


def scan_references(root: Path, include_processed: bool = False) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    references = read_reference_rows(root)
    by_path = {row.get("path", ""): row for row in references}
    seen_paths: set[str] = set()
    new_or_changed: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    references_root = root / "references"
    for path in sorted(references_root.glob("**/*")) if references_root.exists() else []:
        if not path.is_file():
            continue
        rel_path = str(path.relative_to(root))
        seen_paths.add(rel_path)
        digest = _sha256_file(path)
        row = by_path.get(rel_path)
        if row is None:
            row = {
                "reference_id": _next_id(references, "reference_id", "REF"),
                "path": rel_path,
                "sha256": digest,
                "title": "",
                "brief": "",
                "status": "new",
                "updated_at": now_iso(),
            }
            references.append(row)
            by_path[rel_path] = row
            new_or_changed.append(_reference_result(row))
            continue
        if row.get("sha256") != digest:
            row["sha256"] = digest
            row["status"] = "changed"
            row["updated_at"] = now_iso()
            new_or_changed.append(_reference_result(row))
            continue
        row["status"] = row.get("status") or "processed"
        unchanged.append(_reference_result(row))
    for row in references:
        if row.get("path") and row.get("path") not in seen_paths and row.get("status") != "missing":
            row["status"] = "missing"
            row["updated_at"] = now_iso()
    _write_csv_rows(root / "knowledge_base" / "tables" / "references.csv", REFERENCE_FIELDS, references)
    return {
        "new_or_changed": new_or_changed if not include_processed else [*new_or_changed, *unchanged],
        "unchanged": unchanged,
        "counts": {"newOrChanged": len(new_or_changed), "unchanged": len(unchanged)},
    }


def update_reference_brief(root: Path, reference_id: str, title: str, brief: str) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    references = read_reference_rows(root)
    row = _find_row(references, "reference_id", reference_id)
    if not row:
        raise RuntimeError(f"Unknown reference_id: {reference_id}")
    row["title"] = title.strip()
    row["brief"] = brief.strip()
    row["status"] = "processed"
    row["updated_at"] = now_iso()
    _write_csv_rows(root / "knowledge_base" / "tables" / "references.csv", REFERENCE_FIELDS, references)
    return _reference_result(row)


def extract_reference_text(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    reference = _resolve_reference(root, str(args.get("reference_id", "") or ""), str(args.get("path", "") or ""))
    path = root / reference["path"]
    max_chars_per_page = int(args.get("max_chars_per_page") or 2400)
    pages_arg = str(args.get("pages", "") or "").strip()
    if not path.exists():
        raise RuntimeError(f"reference file not found: {reference['path']}")
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        return {
            "reference_id": reference["reference_id"],
            "path": reference["path"],
            "method": "text_file",
            "ok": bool(text.strip()),
            "pages": [{"page": 1, "text": text[:max_chars_per_page], "char_count": len(text)}],
            "cache_path": _write_reference_text_cache(root, reference["reference_id"], {1: text}),
        }
    if suffix != ".pdf":
        raise RuntimeError(f"Unsupported reference text extraction type: {suffix or 'unknown'}")
    page_count = _pdf_page_count(path)
    selected_pages = _parse_page_selection(pages_arg, page_count)
    page_texts: dict[int, str] = {}
    for page in selected_pages:
        text = _pdftotext_page(path, page)
        page_texts[page] = text
    cache_path = _write_reference_text_cache(root, reference["reference_id"], page_texts)
    pages = [
        {"page": page, "text": text[:max_chars_per_page], "char_count": len(text)}
        for page, text in page_texts.items()
    ]
    return {
        "reference_id": reference["reference_id"],
        "path": reference["path"],
        "method": "pdftotext",
        "ok": any(item["char_count"] > 0 for item in pages),
        "page_count": page_count,
        "pages": pages,
        "cache_path": cache_path,
        "note": "" if any(item["char_count"] > 0 for item in pages) else "No text layer extracted by pdftotext. Use SDK Read only as visual fallback or add OCR tooling.",
    }


def add_evidence(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    evidence = read_evidence_rows(root)
    source = _normalize_reference_path(root, str(args.get("reference_file", "")))
    if not source:
        raise RuntimeError("add_evidence requires reference_file.")
    if source.startswith("references/") and not (root / source).exists():
        raise RuntimeError(f"reference_file not found: {source}")
    row = {
        "evidence_id": _next_id(evidence, "evidence_id", "E"),
        "reference_file": source,
        "page": str(args.get("page", "") or ""),
        "section": str(args.get("section", "") or ""),
        "quoted_fragments": _json_list(args.get("quoted_fragments", [])),
        "notes": str(args.get("notes", "") or ""),
    }
    evidence.append(row)
    _write_csv_rows(root / "knowledge_base" / "tables" / "evidence.csv", EVIDENCE_FIELDS, evidence)
    return {"evidence_id": row["evidence_id"], "reference_file": source}


def add_knowledge(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    knowledge = read_knowledge_rows(root)
    evidence_ids = _normalize_id_list(args.get("evidence_ids", []))
    _require_existing_ids(evidence_ids, {row.get("evidence_id", "") for row in read_evidence_rows(root)}, "evidence_ids")
    row = {
        "knowledge_id": _next_id(knowledge, "knowledge_id", "K"),
        "topic": str(args.get("topic", "") or "").strip(),
        "description": str(args.get("description", "") or "").strip(),
        "summary": str(args.get("summary", "") or "").strip() or str(args.get("description", "") or "").strip()[:480],
        "evidence_ids": _json_list(evidence_ids),
        "class_ids": _json_list([]),
        "relation_ids": _json_list([]),
        "status": "pending_graph",
        "notes": str(args.get("notes", "") or "").strip(),
    }
    if not row["topic"] or not row["description"]:
        raise RuntimeError("add_knowledge requires topic and description.")
    knowledge.append(row)
    _write_csv_rows(root / "knowledge_base" / "tables" / "knowledge.csv", KNOWLEDGE_FIELDS, knowledge)
    return {"knowledge_id": row["knowledge_id"], "status": row["status"]}


def list_pending_knowledge(root: Path, limit: int = 10) -> list[dict[str, Any]]:
    ensure_knowledge_base_layout(root)
    out: list[dict[str, Any]] = []
    for row in read_knowledge_rows(root):
        if (row.get("status") or "pending_graph") != "pending_graph":
            continue
        out.append(_knowledge_compact(row))
        if len(out) >= max(1, limit):
            break
    return out


def get_knowledge(root: Path, knowledge_id: str, detail: str = "compact") -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    row = _find_row(read_knowledge_rows(root), "knowledge_id", knowledge_id)
    if not row:
        raise RuntimeError(f"Unknown knowledge_id: {knowledge_id}")
    if detail == "full":
        return _knowledge_full(row)
    return _knowledge_compact(row)


def search_classes(root: Path, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    ensure_knowledge_base_layout(root)
    terms = _terms(query)
    normalized_query = _normalize_label(query)
    scored: list[tuple[int, dict[str, str]]] = []
    for row in read_class_rows(root):
        aliases = " ".join(_split_ids(row.get("aliases", "")))
        haystack = _fold_text(" ".join([row.get("class_id", ""), row.get("label", ""), row.get("normalized_label", ""), row.get("concept_type", ""), aliases, row.get("description", "")]))
        score = sum(haystack.count(term) for term in terms)
        if row.get("normalized_label") == normalized_query:
            score += 100
        if normalized_query and normalized_query in [_normalize_label(alias) for alias in _split_ids(row.get("aliases", ""))]:
            score += 60
        if score:
            scored.append((score, row))
    return [_class_result(row, score) for score, row in sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]]


def upsert_class(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    classes = read_class_rows(root)
    knowledge = read_knowledge_rows(root)
    max_depth = _graph_extraction_depth(root)
    label = str(args.get("label", "") or "").strip()
    normalized = _normalize_label(label)
    if not normalized:
        raise RuntimeError("upsert_class requires label.")
    concept_level = _bounded_int(args.get("concept_level"), default=1, minimum=1, maximum=4)
    if concept_level > max_depth:
        raise RuntimeError(f"concept_level {concept_level} exceeds configured extraction depth {max_depth}.")
    concept_type = _normalize_concept_type(str(args.get("concept_type", "") or "entity"))
    knowledge_ids = _normalize_id_list(args.get("source_knowledge_ids", []))
    evidence_ids = _merged_ids(_normalize_id_list(args.get("evidence_ids", [])), _evidence_ids_for_knowledge(knowledge, knowledge_ids))
    _require_existing_ids(knowledge_ids, {row.get("knowledge_id", "") for row in knowledge}, "source_knowledge_ids")
    _require_existing_ids(evidence_ids, {row.get("evidence_id", "") for row in read_evidence_rows(root)}, "evidence_ids")
    row = next((item for item in classes if item.get("normalized_label") == normalized), None)
    created = False
    if row is None:
        row = {
            "class_id": _next_id(classes, "class_id", "C"),
            "label": label,
            "normalized_label": normalized,
            "concept_level": str(concept_level),
            "concept_type": concept_type,
            "description": "",
            "source_knowledge_ids": _json_list([]),
            "evidence_ids": _json_list([]),
            "aliases": _json_list([]),
        }
        classes.append(row)
        created = True
    row["label"] = row.get("label") or label
    row["concept_level"] = str(min(_bounded_int(row.get("concept_level"), default=concept_level, minimum=1, maximum=4), concept_level))
    row["concept_type"] = row.get("concept_type") or concept_type
    row["description"] = _merge_text(row.get("description", ""), str(args.get("description_addition", "") or ""))
    row["source_knowledge_ids"] = _json_list(_merged_ids(_split_ids(row.get("source_knowledge_ids", "")), knowledge_ids))
    row["evidence_ids"] = _json_list(_merged_ids(_split_ids(row.get("evidence_ids", "")), evidence_ids))
    row["aliases"] = _json_list(_merged_ids(_split_ids(row.get("aliases", "")), _normalize_id_list(args.get("aliases", []))))
    _write_csv_rows(root / "knowledge_base" / "tables" / "classes.csv", CLASS_FIELDS, classes)
    _update_knowledge_links(root, knowledge_ids, class_ids=[row["class_id"]])
    return {"class_id": row["class_id"], "label": row["label"], "concept_level": row["concept_level"], "concept_type": row["concept_type"], "created": created}


def search_relations(root: Path, source_class_id: str = "", target_class_id: str = "", relation_type: str = "") -> list[dict[str, Any]]:
    ensure_knowledge_base_layout(root)
    relation_type = _normalize_relation_type(relation_type)
    out: list[dict[str, Any]] = []
    class_labels = {row.get("class_id", ""): row.get("label", "") for row in read_class_rows(root)}
    for row in read_relation_rows(root):
        if source_class_id and row.get("source_class_id") != source_class_id:
            continue
        if target_class_id and row.get("target_class_id") != target_class_id:
            continue
        if relation_type and row.get("relation_type") != relation_type:
            continue
        out.append(_relation_result(row, class_labels))
    return out[:10]


def upsert_relation(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    relations = read_relation_rows(root)
    knowledge = read_knowledge_rows(root)
    classes = read_class_rows(root)
    max_depth = _graph_extraction_depth(root)
    class_ids = {row.get("class_id", "") for row in classes}
    source = str(args.get("source_class_id", "") or "").strip()
    target = str(args.get("target_class_id", "") or "").strip()
    relation_type = _normalize_relation_type(str(args.get("relation_type", "") or "related_to"))
    relation_depth = _bounded_int(args.get("relation_depth"), default=max(_class_level(classes, source), _class_level(classes, target)), minimum=1, maximum=4)
    if relation_depth > max_depth:
        raise RuntimeError(f"relation_depth {relation_depth} exceeds configured extraction depth {max_depth}.")
    if source not in class_ids or target not in class_ids:
        raise RuntimeError(f"upsert_relation requires existing source/target classes: {source}, {target}")
    knowledge_ids = _normalize_id_list(args.get("source_knowledge_ids", []))
    evidence_ids = _merged_ids(_normalize_id_list(args.get("evidence_ids", [])), _evidence_ids_for_knowledge(knowledge, knowledge_ids))
    _require_existing_ids(knowledge_ids, {row.get("knowledge_id", "") for row in knowledge}, "source_knowledge_ids")
    _require_existing_ids(evidence_ids, {row.get("evidence_id", "") for row in read_evidence_rows(root)}, "evidence_ids")
    row = next((
        item for item in relations
        if item.get("source_class_id") == source and item.get("target_class_id") == target and item.get("relation_type") == relation_type
    ), None)
    created = False
    if row is None:
        row = {
            "relation_id": _next_id(relations, "relation_id", "R"),
            "source_class_id": source,
            "relation_type": relation_type,
            "target_class_id": target,
            "relation_depth": str(relation_depth),
            "description": "",
            "source_knowledge_ids": _json_list([]),
            "evidence_ids": _json_list([]),
        }
        relations.append(row)
        created = True
    row["relation_depth"] = str(min(_bounded_int(row.get("relation_depth"), default=relation_depth, minimum=1, maximum=4), relation_depth))
    row["description"] = _merge_text(row.get("description", ""), str(args.get("description_addition", "") or ""))
    row["source_knowledge_ids"] = _json_list(_merged_ids(_split_ids(row.get("source_knowledge_ids", "")), knowledge_ids))
    row["evidence_ids"] = _json_list(_merged_ids(_split_ids(row.get("evidence_ids", "")), evidence_ids))
    _write_csv_rows(root / "knowledge_base" / "tables" / "relations.csv", RELATION_FIELDS, relations)
    _update_knowledge_links(root, knowledge_ids, relation_ids=[row["relation_id"]])
    return {"relation_id": row["relation_id"], "created": created}


def validate_knowledge_base(root: Path) -> dict[str, Any]:
    report = validate_knowledge_base_report(root)
    if report["errors"]:
        if any("has extra columns" in error for error in report["errors"]):
            raise RuntimeError("Knowledge CSV formatting failed: " + "; ".join(report["errors"][:12]))
        raise RuntimeError("Knowledge base validation failed: " + "; ".join(report["errors"][:12]))
    return report


def validate_knowledge_base_report(root: Path) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    references = read_reference_rows(root)
    evidence = read_evidence_rows(root)
    knowledge = read_knowledge_rows(root)
    classes = read_class_rows(root)
    relations = read_relation_rows(root)
    errors: list[str] = []
    warnings: list[str] = []
    _collect_csv_shape_errors({
        "references.csv": references,
        "evidence.csv": evidence,
        "knowledge.csv": knowledge,
        "classes.csv": classes,
        "relations.csv": relations,
    }, errors)
    _collect_csv_reference_errors(evidence, knowledge, classes, relations, errors)
    _collect_isolated_class_errors(knowledge, classes, relations, errors)
    for row in evidence:
        source = _normalize_reference_path(root, row.get("reference_file", ""))
        if source.startswith("references/") and not (root / source).exists():
            errors.append(f"{row.get('evidence_id', 'evidence')}.reference_file missing: {source}")
    for row in classes:
        inherited = _merged_evidence_ids(row.get("evidence_ids", ""), row.get("source_knowledge_ids", ""), {
            item.get("knowledge_id", ""): _split_ids(item.get("evidence_ids", ""))
            for item in knowledge
        })
        if not _split_ids(inherited):
            warnings.append(f"{row.get('class_id', 'class')} has no evidence.")
        level = _bounded_int(row.get("concept_level"), default=1, minimum=1, maximum=4)
        if level > _graph_extraction_depth(root):
            errors.append(f"{row.get('class_id', 'class')}.concept_level exceeds configured extraction depth: {level}")
        concept_type = row.get("concept_type", "") or "entity"
        if concept_type not in CONCEPT_TYPES:
            errors.append(f"{row.get('class_id', 'class')}.concept_type unsupported: {concept_type}")
    for row in relations:
        depth = _bounded_int(row.get("relation_depth"), default=1, minimum=1, maximum=4)
        if depth > _graph_extraction_depth(root):
            errors.append(f"{row.get('relation_id', 'relation')}.relation_depth exceeds configured extraction depth: {depth}")
    _collect_depth_coverage_warnings(root, knowledge, classes, warnings)
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def finalize_knowledge_base(root: Path) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    _inherit_class_and_relation_evidence(root)
    report = validate_knowledge_base_report(root)
    if report["errors"]:
        raise RuntimeError("Knowledge base validation failed: " + "; ".join(report["errors"][:12]))
    kb = root / "knowledge_base"
    references = read_reference_rows(root)
    evidence = read_evidence_rows(root)
    knowledge = read_knowledge_rows(root)
    classes = read_class_rows(root)
    relations = read_relation_rows(root)
    manifest = {
        "updatedAt": now_iso(),
        "schemaVersion": 5,
        "extractionDepth": _graph_extraction_depth(root),
        "referenceCount": len(references),
        "evidenceCount": len(evidence),
        "knowledgeCount": len(knowledge),
        "classCount": len(classes),
        "relationCount": len(relations),
        "paths": {
            "references": "knowledge_base/tables/references.csv",
            "evidence": "knowledge_base/tables/evidence.csv",
            "knowledge": "knowledge_base/tables/knowledge.csv",
            "classes": "knowledge_base/tables/classes.csv",
            "relations": "knowledge_base/tables/relations.csv",
        },
        "validation": report,
    }
    (kb / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_keyword_index(root)
    return manifest


def read_knowledge_base_summary(root: Path) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    kb = root / "knowledge_base"
    manifest = _read_json(kb / "manifest.json") or {}
    references = read_reference_rows(root)
    evidence = read_evidence_rows(root)
    knowledge = read_knowledge_rows(root)
    classes = read_class_rows(root)
    relations = read_relation_rows(root)
    return {
        "manifest": manifest,
        "domainBrief": _read_text(kb / "domain-brief.md"),
        "extractionDepth": _graph_extraction_depth(root),
        "referenceCount": len(references),
        "evidenceCount": len(evidence),
        "knowledgeCount": len(knowledge),
        "classCount": len(classes),
        "relationCount": len(relations),
        "evidenceNoteCount": len(evidence),
        "knowledgeNoteCount": len(knowledge),
        "graphEdgeCount": len(relations),
        "recentEvidenceNotes": [row.get("evidence_id", "") for row in evidence[-8:]],
        "recentKnowledgeNotes": [row.get("knowledge_id", "") for row in knowledge[-8:]],
    }


def read_knowledge_base_cards(root: Path, kind: str, limit: int = 200) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    normalized = kind.strip().lower()
    if normalized in {"knowledge", "knowledge_notes"}:
        cards = [
            {
                "id": row.get("knowledge_id", ""),
                "title": row.get("topic", "") or row.get("knowledge_id", ""),
                "subtitle": row.get("status", ""),
                "body": row.get("summary") or row.get("description", "")[:600],
                "meta": {
                    "evidence": _split_ids(row.get("evidence_ids", "")),
                    "classes": _split_ids(row.get("class_ids", "")),
                    "relations": _split_ids(row.get("relation_ids", "")),
                },
            }
            for row in read_knowledge_rows(root)
        ]
        label = "Knowledge"
    elif normalized in {"evidence", "evidence_notes"}:
        cards = []
        for row in read_evidence_rows(root):
            source_path = _normalize_reference_path(root, row.get("reference_file", ""))
            fragments = _parse_json_list(row.get("quoted_fragments", ""))
            cards.append({
                "id": row.get("evidence_id", ""),
                "title": row.get("evidence_id", ""),
                "subtitle": source_path,
                "body": " | ".join(fragments[:2]) if fragments else row.get("notes", ""),
                "meta": {"page": row.get("page", ""), "section": row.get("section", "")},
                "sourcePath": source_path,
                "previewUrl": _reference_preview_url(source_path, row.get("page", "")),
            })
        label = "Evidence"
    elif normalized in {"classes", "class"}:
        cards = [
            {
                "id": row.get("class_id", ""),
                "title": row.get("label", "") or row.get("class_id", ""),
                "subtitle": row.get("normalized_label", ""),
                "body": row.get("description", ""),
                "meta": {
                    "level": row.get("concept_level", "") or "1",
                    "type": row.get("concept_type", "") or "entity",
                    "knowledge": _split_ids(row.get("source_knowledge_ids", "")),
                    "evidence": _split_ids(row.get("evidence_ids", "")),
                    "aliases": _split_ids(row.get("aliases", "")),
                },
            }
            for row in read_class_rows(root)
        ]
        label = "Classes"
    elif normalized in {"relations", "relation"}:
        class_labels = {row.get("class_id", ""): row.get("label", "") for row in read_class_rows(root)}
        cards = [
            {
                "id": row.get("relation_id", ""),
                "title": f"{class_labels.get(row.get('source_class_id', ''), row.get('source_class_id', ''))} -> {class_labels.get(row.get('target_class_id', ''), row.get('target_class_id', ''))}",
                "subtitle": row.get("relation_type", ""),
                "body": row.get("description", ""),
                "meta": {
                    "depth": row.get("relation_depth", "") or "1",
                    "knowledge": _split_ids(row.get("source_knowledge_ids", "")),
                    "evidence": _split_ids(row.get("evidence_ids", "")),
                },
            }
            for row in read_relation_rows(root)
        ]
        label = "Relations"
    else:
        raise RuntimeError(f"Unknown knowledge base card kind: {kind}")
    return {"kind": normalized, "label": label, "count": len(cards), "cards": cards[:max(1, limit)]}


def read_graph_view(root: Path) -> dict[str, Any]:
    ensure_knowledge_base_layout(root)
    classes = read_class_rows(root)
    edges = read_relation_rows(root)
    class_labels = {row.get("class_id", ""): row.get("label", "") for row in classes}
    knowledge_evidence = {
        row.get("knowledge_id", ""): _split_ids(row.get("evidence_ids", ""))
        for row in read_knowledge_rows(root)
    }
    nodes: dict[str, dict[str, Any]] = {}
    for row in classes:
        class_id = row.get("class_id", "").strip()
        if not class_id:
            continue
        evidence_ids = _merged_evidence_ids(row.get("evidence_ids", ""), row.get("source_knowledge_ids", ""), knowledge_evidence)
        nodes[class_id] = {
            "id": class_id,
            "label": row.get("label") or class_id,
            "type": "class",
            "conceptLevel": row.get("concept_level", "") or "1",
            "conceptType": row.get("concept_type", "") or "entity",
            "summary": row.get("description") or "",
            "evidence": evidence_items(root, evidence_ids),
            "evidenceIds": evidence_ids,
            "knowledgeIds": _split_ids(row.get("source_knowledge_ids", "")),
            "aliases": _split_ids(row.get("aliases", "")),
        }
    graph_edges: list[dict[str, Any]] = []
    for row in edges:
        source = row.get("source_class_id", "").strip()
        target = row.get("target_class_id", "").strip()
        if not source or not target:
            continue
        nodes.setdefault(source, {"id": source, "label": source, "type": "class", "summary": "", "evidence": []})
        nodes.setdefault(target, {"id": target, "label": target, "type": "class", "summary": "", "evidence": []})
        graph_edges.append({
            "id": row.get("relation_id") or f"{source}-{row.get('relation_type', 'related')}-{target}",
            "source": source,
            "target": target,
            "sourceLabel": class_labels.get(source) or source,
            "targetLabel": class_labels.get(target) or target,
            "relation": row.get("relation_type") or "related",
            "relationDepth": row.get("relation_depth", "") or "1",
            "summary": row.get("description") or "",
            "evidence": evidence_items(root, row.get("evidence_ids", "")),
            "knowledgeIds": _split_ids(row.get("source_knowledge_ids", "")),
            "evidenceIds": _split_ids(row.get("evidence_ids", "")),
        })
    summary = read_knowledge_base_summary(root)
    return {
        "version": 2,
        "taskGoal": _first_heading(summary["domainBrief"]) or "Knowledge Base",
        "updatedAt": summary["manifest"].get("updatedAt"),
        "sourcePaths": ["knowledge_base/domain-brief.md", "knowledge_base/tables/classes.csv", "knowledge_base/tables/relations.csv"],
        "nodes": list(nodes.values()),
        "edges": graph_edges,
        "summary": summary,
        "notes": "CSV knowledge base: evidence, knowledge, class nodes, and relation edges.",
    }


def search_knowledge_notes(root: Path, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    terms = _terms(query)
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in read_knowledge_rows(root):
        haystack = _fold_text(" ".join(str(row.get(key, "")) for key in ("knowledge_id", "topic", "summary", "description", "notes", "evidence_ids", "class_ids", "relation_ids")))
        score = sum(haystack.count(term) for term in terms)
        if score:
            scored.append((score, row))
    return [_knowledge_result(row, score) for score, row in sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]]


def search_evidence_notes(root: Path, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    terms = _terms(query)
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in read_evidence_rows(root):
        haystack = _fold_text(" ".join(str(row.get(key, "")) for key in EVIDENCE_FIELDS))
        score = sum(haystack.count(term) for term in terms)
        if score:
            scored.append((score, row))
    return [_evidence_result(row, score) for score, row in sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]]


def search_graph(root: Path, query: str, relation_type: str | None = None, top_k: int = 10) -> list[dict[str, Any]]:
    terms = _terms(query)
    normalized_relation_type = _normalize_relation_type(relation_type) if relation_type else None
    matches: list[tuple[int, dict[str, Any]]] = []
    class_labels = {row.get("class_id", ""): row.get("label", "") for row in read_class_rows(root)}
    for row in read_relation_rows(root):
        if normalized_relation_type and row.get("relation_type") != normalized_relation_type:
            continue
        haystack = _fold_text(" ".join([
            str(row.get(key, "")) for key in RELATION_FIELDS
        ] + [class_labels.get(row.get("source_class_id", ""), ""), class_labels.get(row.get("target_class_id", ""), "")]))
        score = sum(1 for term in terms if term in haystack)
        if score:
            matches.append((score, row))
    return [row for _, row in sorted(matches, key=lambda item: item[0], reverse=True)[:top_k]]


def get_neighbors(root: Path, concept: str, depth: int = 1) -> dict[str, Any]:
    normalized_concept = _normalize_label(concept)
    matched_class = next((
        row for row in read_class_rows(root)
        if row.get("class_id", "").casefold() == concept.casefold()
        or row.get("normalized_label", "") == normalized_concept
        or normalized_concept in {_normalize_label(alias) for alias in _split_ids(row.get("aliases", ""))}
    ), None)
    resolved_concept = matched_class.get("class_id", concept) if matched_class else concept
    frontier = {resolved_concept.casefold()}
    seen = set(frontier)
    edges_out: list[dict[str, Any]] = []
    for _ in range(max(1, depth)):
        next_frontier: set[str] = set()
        for row in read_relation_rows(root):
            source = row.get("source_class_id", "")
            target = row.get("target_class_id", "")
            if source.lower() in frontier or target.lower() in frontier:
                edges_out.append(row)
                for item in (source, target):
                    lowered = item.lower()
                    if lowered not in seen:
                        seen.add(lowered)
                        next_frontier.add(lowered)
        frontier = next_frontier
    return {"concept": concept, "resolvedClassId": resolved_concept, "neighbors": sorted(seen - {resolved_concept.casefold()}), "edges": edges_out}


def get_supporting_evidence(root: Path, note_or_edge_id: str, top_k: int = 8) -> list[dict[str, Any]]:
    edge = next((row for row in read_relation_rows(root) if row.get("relation_id") == note_or_edge_id), None)
    evidence_ids = _split_ids(edge.get("evidence_ids", "")) if edge else []
    if not evidence_ids and note_or_edge_id.startswith("K-"):
        knowledge = next((row for row in read_knowledge_rows(root) if row.get("knowledge_id") == note_or_edge_id), None)
        evidence_ids = _split_ids(knowledge.get("evidence_ids", "")) if knowledge else []
    results = []
    evidence_by_id = {row.get("evidence_id", ""): row for row in read_evidence_rows(root)}
    for evidence_id in evidence_ids[:top_k]:
        row = evidence_by_id.get(evidence_id)
        if row:
            results.append(_evidence_result(row, score=1))
    return results


def suggest_next_checks(root: Path, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    notes = search_knowledge_notes(root, query, top_k=top_k * 2)
    out: list[dict[str, Any]] = []
    for note in notes:
        text = note.get("text", "")
        if text:
            out.append({"note_id": note["note_id"], "topic": note.get("topic"), "recommended_check": text[:800]})
        if len(out) >= top_k:
            break
    return out


def retrieve_knowledge_context(root: Path, query: str, top_k: int = 5) -> dict[str, Any]:
    knowledge = search_knowledge_notes(root, query, top_k=top_k)
    evidence = search_evidence_notes(root, query, top_k=top_k)
    graph = search_graph(root, query, top_k=top_k)
    checks = suggest_next_checks(root, query, top_k=top_k)
    return {"knowledge_notes": knowledge, "evidence_notes": evidence, "graph_edges": graph, "recommended_next_checks": checks}


def read_evidence_rows(root: Path) -> list[dict[str, str]]:
    return _read_csv_rows(root / "knowledge_base" / "tables" / "evidence.csv", EVIDENCE_FIELDS)


def read_reference_rows(root: Path) -> list[dict[str, str]]:
    return _read_csv_rows(root / "knowledge_base" / "tables" / "references.csv", REFERENCE_FIELDS)


def read_knowledge_rows(root: Path) -> list[dict[str, str]]:
    return _read_csv_rows(root / "knowledge_base" / "tables" / "knowledge.csv", KNOWLEDGE_FIELDS)


def read_class_rows(root: Path) -> list[dict[str, str]]:
    return _read_csv_rows(root / "knowledge_base" / "tables" / "classes.csv", CLASS_FIELDS)


def read_relation_rows(root: Path) -> list[dict[str, str]]:
    return _read_csv_rows(root / "knowledge_base" / "tables" / "relations.csv", RELATION_FIELDS)


def _read_csv_rows(path: Path, fields: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for row in reader:
            clean = {field: str(row.get(field, "") or "") for field in fields}
            extras = row.get(None)
            if extras:
                clean["__extra_columns__"] = json.dumps([str(item) for item in extras], ensure_ascii=False)
            rows.append(clean)
        return rows


def _ensure_csv_header(path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    _write_csv_rows(path, fields, [])


def _write_csv_rows(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: str(row.get(field, "") or "") for field in fields})


def _next_id(rows: list[dict[str, str]], field: str, prefix: str) -> str:
    max_id = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for row in rows:
        match = pattern.match(row.get(field, ""))
        if match:
            max_id = max(max_id, int(match.group(1)))
    return f"{prefix}-{max_id + 1:05d}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_reference(root: Path, reference_id: str, source_path: str) -> dict[str, str]:
    references = read_reference_rows(root)
    if reference_id:
        row = _find_row(references, "reference_id", reference_id)
        if row:
            return row
        raise RuntimeError(f"Unknown reference_id: {reference_id}")
    normalized = _normalize_reference_path(root, source_path)
    row = _find_row(references, "path", normalized)
    if row:
        return row
    if normalized and (root / normalized).exists():
        scan_references(root, include_processed=True)
        row = _find_row(read_reference_rows(root), "path", normalized)
        if row:
            return row
    raise RuntimeError("extract_reference_text requires reference_id or known path.")


def _pdf_page_count(path: Path) -> int:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return 1
    result = subprocess.run([pdfinfo, str(path)], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return 1
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.M)
    return int(match.group(1)) if match else 1


def _parse_page_selection(selection: str, page_count: int) -> list[int]:
    if not selection:
        return list(range(1, max(1, page_count) + 1))
    pages: set[int] = set()
    for part in selection.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = chunk.split("-", 1)
            try:
                start_i = int(start)
                end_i = int(end)
            except ValueError:
                continue
            pages.update(range(max(1, start_i), min(page_count, end_i) + 1))
            continue
        try:
            page = int(chunk)
        except ValueError:
            continue
        if 1 <= page <= page_count:
            pages.add(page)
    return sorted(pages) or list(range(1, max(1, page_count) + 1))


def _pdftotext_page(path: Path, page: int) -> str:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise RuntimeError("pdftotext is not available; install poppler to extract PDF text.")
    result = subprocess.run(
        [pdftotext, "-layout", "-f", str(page), "-l", str(page), str(path), "-"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed for page {page}: {result.stderr.strip()}")
    return result.stdout.strip()


def _write_reference_text_cache(root: Path, reference_id: str, page_texts: dict[int, str]) -> str:
    cache_dir = root / "knowledge_base" / "cache" / "reference_text" / reference_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    for page, text in page_texts.items():
        (cache_dir / f"page-{page:03d}.txt").write_text(text + ("\n" if text else ""), encoding="utf-8")
    combined = "\n\n".join([f"--- Page {page} ---\n{text}" for page, text in sorted(page_texts.items())])
    (cache_dir / "all.txt").write_text(combined + ("\n" if combined else ""), encoding="utf-8")
    return str((cache_dir / "all.txt").relative_to(root))


def _reference_result(row: dict[str, str]) -> dict[str, Any]:
    return {
        "reference_id": row.get("reference_id", ""),
        "path": row.get("path", ""),
        "sha256": row.get("sha256", ""),
        "title": row.get("title", ""),
        "brief": row.get("brief", ""),
        "status": row.get("status", ""),
    }


def _find_row(rows: list[dict[str, str]], field: str, value: str) -> dict[str, str] | None:
    return next((row for row in rows if row.get(field) == value), None)


def _json_list(value: Any) -> str:
    return json.dumps(_normalize_id_list(value), ensure_ascii=False)


def _normalize_id_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        if value.strip().startswith("["):
            return _parse_json_list(value)
        if not value.strip():
            return []
        return [value.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _require_existing_ids(ids: list[str], valid_ids: set[str], field: str) -> None:
    missing = [item for item in ids if item not in valid_ids]
    if missing:
        raise RuntimeError(f"{field} contain unknown ids: {', '.join(missing)}")


def _merged_ids(left: list[str], right: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in [*left, *right]:
        normalized = str(item).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _merge_text(existing: str, addition: str) -> str:
    existing = existing.strip()
    addition = addition.strip()
    if not addition:
        return existing
    if not existing:
        return addition
    if addition.lower() in existing.lower():
        return existing
    return f"{existing}\n\n{addition}"


def _normalize_label(value: str) -> str:
    normalized = "".join(
        character.upper() if character.isalnum() else "-"
        for character in unicodedata.normalize("NFKC", value).strip()
    ).strip("-")
    return re.sub(r"-+", "-", normalized)


def _normalize_relation_type(value: str) -> str:
    rel = _normalize_unicode_key(value)
    aliases = {
        "is_a": "subclass_of",
        "type_of": "subclass_of",
        "component_of": "part_of",
        "indicates": "supports",
        "suggests": "supports",
        "may_be_confused_with": "confounds",
        "should_check": "requires_check",
        "属于": "subclass_of",
        "是一种": "subclass_of",
        "组成部分": "part_of",
        "支持": "supports",
        "提示": "supports",
        "导致": "causes",
        "引起": "causes",
        "相关": "related_to",
        "混淆": "confounds",
        "需要检查": "requires_check",
    }
    return aliases.get(rel, rel or "related_to")


def _normalize_concept_type(value: str) -> str:
    normalized = _normalize_unicode_key(value)
    aliases = {
        "pattern": "abnormality_pattern",
        "abnormality": "abnormality_pattern",
        "feature": "signal_feature",
        "signal": "signal_feature",
        "paper": "evidence_source",
        "reference": "evidence_source",
        "check": "next_check",
        "实体": "entity",
        "异常模式": "abnormality_pattern",
        "信号特征": "signal_feature",
        "波形": "waveform",
        "间期": "interval",
        "阈值": "threshold",
        "条件": "condition",
        "混杂因素": "confounder",
        "任务": "task",
        "数据集": "dataset",
        "方法": "method",
        "证据来源": "evidence_source",
        "机制": "mechanism",
        "下一步检查": "next_check",
    }
    normalized = aliases.get(normalized, normalized or "entity")
    if normalized not in CONCEPT_TYPES:
        raise RuntimeError(f"Unsupported concept_type: {value}.")
    return normalized


def _class_level(classes: list[dict[str, str]], class_id: str) -> int:
    row = next((item for item in classes if item.get("class_id") == class_id), None)
    return _bounded_int(row.get("concept_level") if row else "", default=1, minimum=1, maximum=4)


def _graph_extraction_depth(root: Path) -> int:
    raw = _read_json(root / "state" / "runtime-settings.json") or {}
    return _bounded_int(raw.get("knowledgeGraphExtractionDepth"), default=2, minimum=1, maximum=4)


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


DEPTH_COVERAGE_TERMS = [
    ("P wave", ["p wave", "p-wave", "p 波", "p波"]),
    ("Sinus P wave", ["sinus p wave", "窦性 p 波", "窦性p波"]),
    ("QRS complex", ["qrs complex", "qrs-complex", "qrs 波群", "qrs波群"]),
    ("QRS duration", ["qrs duration", "qrs 宽度", "qrs宽度", "qrs 增宽", "qrs增宽"]),
    ("PR interval", ["pr interval", "pr 间期", "pr间期"]),
    ("RR interval", ["rr interval", "rr 间期", "rr间期", "规律 rr", "规律rr"]),
    ("T wave", ["t wave", "t-wave", "t 波", "t波"]),
    ("Coupling interval", ["coupling interval", "耦合间期"]),
    ("Compensatory pause", ["compensatory pause", "代偿间歇"]),
    ("Premature occurrence", ["premature occurrence", "提前出现", "早搏"]),
    ("Noise artifact", ["noise artifact", "噪声", "伪差"]),
    ("Baseline drift", ["baseline drift", "基线漂移"]),
    ("Aberrant conduction", ["aberrant conduction", "差异性传导", "差传"]),
]


def _collect_depth_coverage_warnings(
    root: Path,
    knowledge: list[dict[str, str]],
    classes: list[dict[str, str]],
    warnings: list[str],
) -> None:
    depth = _graph_extraction_depth(root)
    if depth < 2:
        return
    class_text = "\n".join(
        " ".join([row.get("label", ""), row.get("normalized_label", ""), row.get("description", ""), row.get("aliases", "")]).lower()
        for row in classes
    )
    for row in knowledge:
        text = " ".join([row.get("topic", ""), row.get("summary", ""), row.get("description", "")]).lower()
        missing = [
            canonical for canonical, variants in DEPTH_COVERAGE_TERMS
            if any(variant.lower() in text for variant in variants)
            and not any(variant.lower() in class_text for variant in variants)
        ]
        if missing:
            warnings.append(f"{row.get('knowledge_id', 'knowledge')} may miss depth-{depth} feature classes: {', '.join(missing[:8])}.")


def _evidence_ids_for_knowledge(knowledge_rows: list[dict[str, str]], knowledge_ids: list[str]) -> list[str]:
    by_id = {row.get("knowledge_id", ""): row for row in knowledge_rows}
    out: list[str] = []
    for knowledge_id in knowledge_ids:
        row = by_id.get(knowledge_id)
        if row:
            out = _merged_ids(out, _split_ids(row.get("evidence_ids", "")))
    return out


def _update_knowledge_links(
    root: Path,
    knowledge_ids: list[str],
    *,
    class_ids: list[str] | None = None,
    relation_ids: list[str] | None = None,
) -> None:
    if not knowledge_ids:
        return
    knowledge = read_knowledge_rows(root)
    changed = False
    for row in knowledge:
        if row.get("knowledge_id") not in knowledge_ids:
            continue
        if class_ids:
            row["class_ids"] = _json_list(_merged_ids(_split_ids(row.get("class_ids", "")), class_ids))
        if relation_ids:
            row["relation_ids"] = _json_list(_merged_ids(_split_ids(row.get("relation_ids", "")), relation_ids))
        if _split_ids(row.get("class_ids", "")) and _split_ids(row.get("relation_ids", "")):
            row["status"] = "graph_done"
        changed = True
    if changed:
        _write_csv_rows(root / "knowledge_base" / "tables" / "knowledge.csv", KNOWLEDGE_FIELDS, knowledge)


def _knowledge_compact(row: dict[str, str]) -> dict[str, Any]:
    return {
        "knowledge_id": row.get("knowledge_id", ""),
        "topic": row.get("topic", ""),
        "summary": row.get("summary") or row.get("description", "")[:480],
        "evidence_ids": _split_ids(row.get("evidence_ids", "")),
        "class_ids": _split_ids(row.get("class_ids", "")),
        "relation_ids": _split_ids(row.get("relation_ids", "")),
        "status": row.get("status", ""),
    }


def _knowledge_full(row: dict[str, str]) -> dict[str, Any]:
    out = _knowledge_compact(row)
    out.update({
        "description": row.get("description", ""),
        "notes": row.get("notes", ""),
    })
    return out


def _class_result(row: dict[str, str], score: int = 0) -> dict[str, Any]:
    return {
        "class_id": row.get("class_id", ""),
        "label": row.get("label", ""),
        "normalized_label": row.get("normalized_label", ""),
        "concept_level": row.get("concept_level", "") or "1",
        "concept_type": row.get("concept_type", "") or "entity",
        "description": row.get("description", ""),
        "aliases": _split_ids(row.get("aliases", "")),
        "score": score,
    }


def _relation_result(row: dict[str, str], class_labels: dict[str, str]) -> dict[str, Any]:
    return {
        "relation_id": row.get("relation_id", ""),
        "source_class_id": row.get("source_class_id", ""),
        "source_label": class_labels.get(row.get("source_class_id", ""), row.get("source_class_id", "")),
        "relation_type": row.get("relation_type", ""),
        "target_class_id": row.get("target_class_id", ""),
        "target_label": class_labels.get(row.get("target_class_id", ""), row.get("target_class_id", "")),
        "relation_depth": row.get("relation_depth", "") or "1",
        "description": row.get("description", ""),
        "source_knowledge_ids": _split_ids(row.get("source_knowledge_ids", "")),
        "evidence_ids": _split_ids(row.get("evidence_ids", "")),
    }


def write_keyword_index(root: Path) -> None:
    index = {
        "references": read_reference_rows(root),
        "knowledge": read_knowledge_rows(root),
        "evidence": read_evidence_rows(root),
        "classes": read_class_rows(root),
        "relations": read_relation_rows(root),
        "updatedAt": now_iso(),
    }
    target = root / "knowledge_base" / "indexes" / "keyword_index.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def evidence_items(root: Path, evidence_ids: str) -> list[dict[str, str]]:
    evidence_by_id = {row.get("evidence_id", ""): row for row in read_evidence_rows(root)}
    out: list[dict[str, str]] = []
    for evidence_id in _split_ids(evidence_ids):
        row = evidence_by_id.get(evidence_id)
        if not row:
            continue
        fragments = _parse_json_list(row.get("quoted_fragments", ""))
        source_path = _normalize_reference_path(root, row.get("reference_file", ""))
        out.append({
            "sourcePath": source_path,
            "previewUrl": _reference_preview_url(source_path, row.get("page", "")),
            "quote": " | ".join(fragments[:2]) if fragments else row.get("notes", ""),
            "evidenceId": evidence_id,
            "page": row.get("page", ""),
            "section": row.get("section", ""),
        })
    return out


def _merged_evidence_ids(evidence_ids: str, knowledge_ids: str, knowledge_evidence: dict[str, list[str]]) -> str:
    merged = _split_ids(evidence_ids)
    seen = set(merged)
    for knowledge_id in _split_ids(knowledge_ids):
        for evidence_id in knowledge_evidence.get(knowledge_id, []):
            if evidence_id not in seen:
                merged.append(evidence_id)
                seen.add(evidence_id)
    return json.dumps(merged, ensure_ascii=False)


def _reference_preview_url(source_path: str, page: str = "") -> str:
    normalized = source_path.strip().lstrip("/")
    if normalized.startswith("references/"):
        fragment = _page_fragment(page)
        return "/api/references/preview?path=" + quote(normalized) + fragment
    return ""


def _page_fragment(page: str) -> str:
    match = re.search(r"\d+", page or "")
    return f"#page={int(match.group(0))}" if match else ""


def _normalize_reference_path(root: Path, source_path: str) -> str:
    raw = source_path.strip()
    if not raw:
        return ""
    if re.match(r"^REF-\d+$", raw):
        row = _find_row(read_reference_rows(root), "reference_id", raw)
        if row and row.get("path"):
            return row["path"]
    workspace_root = root.resolve()
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return str(candidate.resolve().relative_to(workspace_root))
        except ValueError:
            return raw
    normalized = raw.lstrip("/")
    if normalized.startswith("references/"):
        return normalized
    basename = Path(normalized).name
    if basename and (workspace_root / "references" / basename).exists():
        return f"references/{basename}"
    return normalized


def _knowledge_result(row: dict[str, str], score: int) -> dict[str, Any]:
    text = row.get("description", "")
    return {
        "note_id": row.get("knowledge_id", ""),
        "path": "knowledge_base/tables/knowledge.csv",
        "score": score,
        "topic": row.get("topic", ""),
        "summary": row.get("summary") or text,
        "matched_text": text[:1200],
        "text": text,
        "evidence_ids": _split_ids(row.get("evidence_ids", "")),
        "class_ids": _split_ids(row.get("class_ids", "")),
        "relation_ids": _split_ids(row.get("relation_ids", "")),
    }


def _evidence_result(row: dict[str, str], score: int) -> dict[str, Any]:
    fragments = _parse_json_list(row.get("quoted_fragments", ""))
    text = "\n".join(fragments) or row.get("notes", "")
    return {
        "note_id": row.get("evidence_id", ""),
        "path": row.get("reference_file", ""),
        "score": score,
        "topic": row.get("reference_file", ""),
        "summary": text[:800],
        "matched_text": text[:1200],
        "text": text,
        "source": row.get("reference_file", ""),
        "page": row.get("page", ""),
        "section": row.get("section", ""),
    }


def _validate_csv_references(
    evidence: list[dict[str, str]],
    knowledge: list[dict[str, str]],
    classes: list[dict[str, str]],
    relations: list[dict[str, str]],
) -> None:
    evidence_ids = {row.get("evidence_id", "") for row in evidence}
    knowledge_ids = {row.get("knowledge_id", "") for row in knowledge}
    class_ids = {row.get("class_id", "") for row in classes}
    relation_ids = {row.get("relation_id", "") for row in relations}
    problems: list[str] = []
    for row in knowledge:
        problems += _missing_refs(row.get("knowledge_id", "knowledge"), "evidence_ids", row.get("evidence_ids", ""), evidence_ids)
        problems += _missing_refs(row.get("knowledge_id", "knowledge"), "class_ids", row.get("class_ids", ""), class_ids)
        problems += _missing_refs(row.get("knowledge_id", "knowledge"), "relation_ids", row.get("relation_ids", ""), relation_ids)
    for row in classes:
        problems += _missing_refs(row.get("class_id", "class"), "source_knowledge_ids", row.get("source_knowledge_ids", ""), knowledge_ids)
        problems += _missing_refs(row.get("class_id", "class"), "evidence_ids", row.get("evidence_ids", ""), evidence_ids)
    for row in relations:
        rel_id = row.get("relation_id", "relation")
        if row.get("source_class_id") not in class_ids:
            problems.append(f"{rel_id}.source_class_id missing: {row.get('source_class_id')}")
        if row.get("target_class_id") not in class_ids:
            problems.append(f"{rel_id}.target_class_id missing: {row.get('target_class_id')}")
        problems += _missing_refs(rel_id, "source_knowledge_ids", row.get("source_knowledge_ids", ""), knowledge_ids)
        problems += _missing_refs(rel_id, "evidence_ids", row.get("evidence_ids", ""), evidence_ids)
    if problems:
        raise RuntimeError("Knowledge CSV reference validation failed: " + "; ".join(problems[:12]))


def _validate_csv_shape(tables: dict[str, list[dict[str, str]]]) -> None:
    problems: list[str] = []
    for table_name, rows in tables.items():
        for index, row in enumerate(rows, start=2):
            extras = row.get("__extra_columns__", "")
            if not extras:
                continue
            row_id = (
                row.get("evidence_id")
                or row.get("knowledge_id")
                or row.get("class_id")
                or row.get("relation_id")
                or f"line {index}"
            )
            problems.append(f"{table_name}:{row_id} has extra columns {extras}")
    if problems:
        raise RuntimeError(
            "Knowledge CSV formatting failed: "
            + "; ".join(problems[:8])
            + ". List fields must be JSON arrays inside one CSV cell, for example [\"E-00001\",\"E-00003\"]."
        )


def _collect_csv_shape_errors(tables: dict[str, list[dict[str, str]]], errors: list[str]) -> None:
    for table_name, rows in tables.items():
        for index, row in enumerate(rows, start=2):
            extras = row.get("__extra_columns__", "")
            if not extras:
                continue
            row_id = (
                row.get("reference_id")
                or row.get("evidence_id")
                or row.get("knowledge_id")
                or row.get("class_id")
                or row.get("relation_id")
                or f"line {index}"
            )
            errors.append(f"{table_name}:{row_id} has extra columns {extras}")


def _collect_csv_reference_errors(
    evidence: list[dict[str, str]],
    knowledge: list[dict[str, str]],
    classes: list[dict[str, str]],
    relations: list[dict[str, str]],
    errors: list[str],
) -> None:
    evidence_ids = {row.get("evidence_id", "") for row in evidence}
    knowledge_ids = {row.get("knowledge_id", "") for row in knowledge}
    class_ids = {row.get("class_id", "") for row in classes}
    relation_ids = {row.get("relation_id", "") for row in relations}
    for row in knowledge:
        errors += _missing_refs(row.get("knowledge_id", "knowledge"), "evidence_ids", row.get("evidence_ids", ""), evidence_ids)
        errors += _missing_refs(row.get("knowledge_id", "knowledge"), "class_ids", row.get("class_ids", ""), class_ids)
        errors += _missing_refs(row.get("knowledge_id", "knowledge"), "relation_ids", row.get("relation_ids", ""), relation_ids)
    for row in classes:
        errors += _missing_refs(row.get("class_id", "class"), "source_knowledge_ids", row.get("source_knowledge_ids", ""), knowledge_ids)
        errors += _missing_refs(row.get("class_id", "class"), "evidence_ids", row.get("evidence_ids", ""), evidence_ids)
    for row in relations:
        rel_id = row.get("relation_id", "relation")
        if row.get("source_class_id") not in class_ids:
            errors.append(f"{rel_id}.source_class_id missing: {row.get('source_class_id')}")
        if row.get("target_class_id") not in class_ids:
            errors.append(f"{rel_id}.target_class_id missing: {row.get('target_class_id')}")
        errors += _missing_refs(rel_id, "source_knowledge_ids", row.get("source_knowledge_ids", ""), knowledge_ids)
        errors += _missing_refs(rel_id, "evidence_ids", row.get("evidence_ids", ""), evidence_ids)


def _collect_isolated_class_errors(
    knowledge: list[dict[str, str]],
    classes: list[dict[str, str]],
    relations: list[dict[str, str]],
    errors: list[str],
) -> None:
    relation_endpoints = {
        endpoint
        for row in relations
        for endpoint in (row.get("source_class_id", ""), row.get("target_class_id", ""))
        if endpoint
    }
    knowledge_by_id = {row.get("knowledge_id", ""): row for row in knowledge}
    for row in classes:
        class_id = row.get("class_id", "class")
        if class_id in relation_endpoints:
            continue
        evidence_ids = _split_ids(row.get("evidence_ids", ""))
        source_knowledge_ids = _split_ids(row.get("source_knowledge_ids", ""))
        for knowledge_id in source_knowledge_ids:
            evidence_ids = _merged_ids(evidence_ids, _split_ids(knowledge_by_id.get(knowledge_id, {}).get("evidence_ids", "")))
        evidence_hint = f" evidence={','.join(evidence_ids[:6])}" if evidence_ids else " evidence=none"
        knowledge_hint = f" source_knowledge={','.join(source_knowledge_ids[:6])}" if source_knowledge_ids else " source_knowledge=none"
        errors.append(
            f"{class_id} has no relation edge. Re-read the class evidence and source knowledge, "
            f"then extract or merge at least one supported relation for this class;{evidence_hint};{knowledge_hint}."
        )


def _inherit_class_and_relation_evidence(root: Path) -> None:
    knowledge = read_knowledge_rows(root)
    knowledge_evidence = {
        row.get("knowledge_id", ""): _split_ids(row.get("evidence_ids", ""))
        for row in knowledge
    }
    classes = read_class_rows(root)
    class_changed = False
    for row in classes:
        inherited = _split_ids(_merged_evidence_ids(row.get("evidence_ids", ""), row.get("source_knowledge_ids", ""), knowledge_evidence))
        if inherited != _split_ids(row.get("evidence_ids", "")):
            row["evidence_ids"] = _json_list(inherited)
            class_changed = True
    if class_changed:
        _write_csv_rows(root / "knowledge_base" / "tables" / "classes.csv", CLASS_FIELDS, classes)
    relations = read_relation_rows(root)
    relation_changed = False
    for row in relations:
        inherited = _split_ids(_merged_evidence_ids(row.get("evidence_ids", ""), row.get("source_knowledge_ids", ""), knowledge_evidence))
        if inherited != _split_ids(row.get("evidence_ids", "")):
            row["evidence_ids"] = _json_list(inherited)
            relation_changed = True
    if relation_changed:
        _write_csv_rows(root / "knowledge_base" / "tables" / "relations.csv", RELATION_FIELDS, relations)
    _mark_finished_knowledge(root)


def _mark_finished_knowledge(root: Path) -> None:
    knowledge = read_knowledge_rows(root)
    changed = False
    for row in knowledge:
        if _split_ids(row.get("class_ids", "")) and _split_ids(row.get("relation_ids", "")) and row.get("status") != "graph_done":
            row["status"] = "graph_done"
            changed = True
    if changed:
        _write_csv_rows(root / "knowledge_base" / "tables" / "knowledge.csv", KNOWLEDGE_FIELDS, knowledge)


def _missing_refs(owner: str, field: str, value: str, valid_ids: set[str]) -> list[str]:
    return [f"{owner}.{field} missing: {item}" for item in _split_ids(value) if item not in valid_ids]


def _parse_json_list(value: str) -> list[str]:
    stripped = (value or "").strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return [item.strip() for item in re.split(r"\s*\n\s*|\s*\|\s*", stripped) if item.strip()]
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return [str(parsed)]


def _ensure_domain_brief(root: Path) -> None:
    target = root / "knowledge_base" / "domain-brief.md"
    if target.exists():
        return
    target.write_text("""# Domain Brief: Time-Series Domain Knowledge

The goal is to extract domain knowledge from reference literature for use by a downstream time-series anomaly detection agent.

Focus on:
- signal features
- abnormality or fault patterns
- diagnostic or decision thresholds
- channel/lead/sensor-specific conditions
- temporal patterns
- confounders and differential patterns
- recommended next checks for the downstream agent

For every knowledge item, include:
- the key concept
- the supporting evidence
- the relation to other concepts
- how this knowledge can help a time-series anomaly detection agent
""", encoding="utf-8")


def _format_retrieved_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- none"
    return "\n\n".join([
        f"## {item.get('note_id')}\nTopic: {item.get('topic')}\nSummary: {item.get('summary')}\nExcerpt:\n{item.get('matched_text')}"
        for item in items
    ])


def _last_assistant_text(parts: list[Part]) -> str:
    for part in reversed(parts):
        if part.get("role") == "assistant" and part.get("text"):
            return str(part["text"])
    return ""


def _parse_json_answer(text: str) -> dict[str, Any]:
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {"answer": stripped}
    except json.JSONDecodeError:
        return {"answer": text, "candidate_targets": [], "supporting_knowledge": [], "supporting_evidence": [], "related_graph_edges": [], "recommended_next_checks": [], "uncertainty": "The reasoning agent did not return valid JSON."}


def _compact_knowledge_query_answer(answer: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {
        "answer": str(answer.get("answer") or ""),
        "candidate_targets": answer.get("candidate_targets") if isinstance(answer.get("candidate_targets"), list) else [],
        "supporting_knowledge": answer.get("supporting_knowledge") if isinstance(answer.get("supporting_knowledge"), list) else [],
        "recommended_next_checks": answer.get("recommended_next_checks") if isinstance(answer.get("recommended_next_checks"), list) else [],
        "uncertainty": str(answer.get("uncertainty") or ""),
        "supporting_evidence": [],
        "related_graph_edges": [],
    }
    return compact


def _terms(query: str) -> list[str]:
    folded = _fold_text(query)
    chunks = re.findall(r"[a-z0-9]+|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", folded)
    terms: list[str] = []
    for chunk in chunks:
        if _contains_cjk(chunk):
            terms.append(chunk)
            if len(chunk) > 2:
                terms.extend(chunk[index:index + 2] for index in range(len(chunk) - 1))
        elif len(chunk) > 1:
            terms.append(chunk)
    return list(dict.fromkeys(terms))[:20]


def _fold_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _contains_cjk(value: str) -> bool:
    return any("\u3400" <= character <= "\u4dbf" or "\u4e00" <= character <= "\u9fff" or "\uf900" <= character <= "\ufaff" for character in value)


def _normalize_unicode_key(value: str) -> str:
    normalized = "".join(
        character if character.isalnum() else "_"
        for character in _fold_text(value).strip()
    ).strip("_")
    return re.sub(r"_+", "_", normalized)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _first_heading(text: str) -> str:
    match = re.search(r"^#++\s+(.+)$", text, re.M)
    return match.group(1).strip() if match else ""


def _split_ids(value: str) -> list[str]:
    stripped = (value or "").strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        return _parse_json_list(stripped)
    return [item.strip() for item in re.split(r"[,;|]+", stripped) if item.strip()]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "concept"
