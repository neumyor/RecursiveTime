from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from harnessing_ts.schema import Part


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def user_text_part(text: str) -> Part:
    return {"id": str(uuid4()), "timestamp": _now(), "role": "user", "type": "text", "text": text}


def system_text_part(text: str) -> Part:
    return {"id": str(uuid4()), "timestamp": _now(), "role": "system", "type": "text", "text": text}


def sdk_message_to_part(message: Any) -> Part:
    raw = _to_jsonable(message)
    msg_type = _get(raw, "type") or _class_type(message)
    timestamp = _now()

    if msg_type == "assistant":
        content = _content(raw)
        tool_use = next((item for item in content if _is_tool_use(item)), None)
        if tool_use:
            input_value = tool_use.get("input")
            intend = _extract_intend(input_value, tool_use.get("name"))
            return {
                "id": str(uuid4()),
                "timestamp": timestamp,
                "role": "assistant",
                "type": "tool_call",
                "name": tool_use.get("name", "tool"),
                "input": input_value,
                "intend": intend,
                "toolUseId": tool_use.get("id"),
                "status": "pending",
                "text": intend,
                "raw": raw,
            }
        return {"id": str(uuid4()), "timestamp": timestamp, "role": "assistant", "type": "text", "text": _extract_visible_text(raw), "raw": raw}

    if msg_type == "result":
        return {"id": str(uuid4()), "timestamp": timestamp, "role": "system", "type": "result", "text": _extract_result_text(raw), "raw": raw}

    if msg_type == "user":
        tool_result = next((item for item in _content(raw) if _is_tool_result(item)), None)
        if tool_result:
            result_text = _format_tool_result(tool_result.get("content"), raw.get("tool_use_result"))
            return {
                "id": str(uuid4()),
                "timestamp": timestamp,
                "role": "tool",
                "type": "tool_result",
                "toolUseId": tool_result.get("tool_use_id"),
                "resultText": result_text,
                "text": result_text,
                "raw": raw,
            }
        return {"id": str(uuid4()), "timestamp": timestamp, "role": "user", "type": "text", "text": _extract_visible_text(raw), "raw": raw}

    return {"id": str(uuid4()), "timestamp": timestamp, "role": "system", "type": "raw", "text": str(raw.get("subtype") or msg_type or ""), "raw": raw}


def merge_tool_result_part(tool_call: Part, tool_result: Part) -> Part:
    merged = dict(tool_call)
    merged["status"] = "completed"
    merged["resultText"] = _strip_reasoning_jsonl_lines(tool_result.get("resultText") or tool_result.get("text") or "")
    merged["resultRaw"] = tool_result.get("raw")
    merged["text"] = merged.get("intend") or _format_tool_use(merged.get("name"), merged.get("input"))
    return merged


def should_merge_tool_result(tool_call: Part, tool_result: Part) -> bool:
    if tool_call.get("type") not in {"tool_call", "tool_use"} or tool_result.get("type") != "tool_result":
        return False
    call_id = tool_call.get("toolUseId") or _tool_use_id_from_raw(tool_call.get("raw"))
    result_id = tool_result.get("toolUseId")
    return isinstance(call_id, str) and call_id != "" and call_id == result_id


def collapse_tool_parts(parts: list[Part]) -> list[Part]:
    out: list[Part] = []
    for part in parts:
        if part.get("type") == "tool_result":
            merged = False
            for index in range(len(out) - 1, -1, -1):
                if should_merge_tool_result(out[index], part):
                    out[index] = merge_tool_result_part(_normalize_tool_call_part(out[index]), part)
                    merged = True
                    break
            if merged:
                continue
        if part.get("type") == "tool_use":
            out.append(_normalize_tool_call_part(part))
        else:
            out.append(part)
    return out


def filter_display_parts(parts: list[Part]) -> list[Part]:
    return [_sanitize_display_part(part) for part in parts if not is_ignorable_display_part(part)]


def _sanitize_display_part(part: Part) -> Part:
    if part.get("type") not in {"tool_call", "tool_result"}:
        return part
    changed = False
    sanitized = dict(part)
    for key in ("resultText", "text"):
        value = sanitized.get(key)
        if isinstance(value, str):
            clean = _strip_reasoning_jsonl_lines(value)
            if clean != value:
                sanitized[key] = clean
                changed = True
    return sanitized if changed else part


def is_ignorable_display_part(part: Part) -> bool:
    if part.get("role") == "system" and part.get("type") == "raw":
        subtype = _raw_subtype(part)
        return subtype in {
            "init",
            "task_started",
            "task_progress",
            "task_updated",
            "task_notification",
            "task_completed",
            "task_failed",
            "task_stopped",
            "task_output",
            "system",
            "thinking_tokens",
        } or subtype.endswith("_tokens")
    if part.get("role") == "assistant" and part.get("type") == "text":
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            return False
        return _raw_contains_only_reasoning_content(part.get("raw"))
    if part.get("role") == "system" and part.get("type") == "result":
        raw = part.get("raw")
        return not (isinstance(raw, dict) and raw.get("is_error") is True)
    return False


def _raw_contains_only_reasoning_content(raw: Any) -> bool:
    content = _content(raw) if isinstance(raw, dict) else []
    if not content:
        return False
    for item in content:
        if isinstance(item, str) and item.strip():
            return False
        if not isinstance(item, dict):
            return False
        if isinstance(item.get("text"), str) and item["text"].strip():
            return False
        if _is_tool_use(item) or _is_tool_result(item):
            return False
        if item.get("type") not in {None, "thinking", "redacted_thinking"} and not any(
            key in item for key in ("thinking", "signature", "redacted_thinking")
        ):
            return False
        if not any(key in item for key in ("thinking", "signature", "redacted_thinking")) and item.get("type") not in {"thinking", "redacted_thinking"}:
            return False
    return True


def _raw_subtype(part: Part) -> str:
    raw = part.get("raw")
    if isinstance(raw, dict) and isinstance(raw.get("subtype"), str):
        return raw["subtype"].strip()
    for key in ("text", "displayText"):
        value = part.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def _class_type(message: Any) -> str:
    name = message.__class__.__name__
    if name.endswith("Message"):
        return name.removesuffix("Message").lower()
    return "raw"


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list | tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if hasattr(value, "__dict__"):
        return {k: _to_jsonable(v) for k, v in vars(value).items() if not k.startswith("_")}
    return repr(value)


def _get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _content(raw: dict[str, Any]) -> list[Any]:
    message = raw.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), list):
        return message["content"]
    if isinstance(raw.get("content"), list):
        return raw["content"]
    return []


def _is_tool_use(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and "input" in item
        and (item.get("type") in {None, "tool_use"} or isinstance(item.get("id"), str))
    )


def _is_tool_result(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and (item.get("type") == "tool_result" or isinstance(item.get("tool_use_id"), str))
        and "content" in item
    )


def _extract_visible_text(raw: dict[str, Any]) -> str:
    value: Any = raw.get("message", raw)
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    if isinstance(value.get("text"), str):
        return value["text"]
    content = value.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def _extract_result_text(raw: dict[str, Any]) -> str:
    if isinstance(raw.get("result"), str):
        return raw["result"]
    if isinstance(raw.get("subtype"), str):
        return raw["subtype"]
    return ""


def _format_tool_use(name: Any, input_value: Any) -> str:
    label = name if isinstance(name, str) else "tool"
    if input_value is None:
        return f"Tool call: {label}"
    import json

    return f"Tool call: {label}\n{json.dumps(input_value, ensure_ascii=False, indent=2)}"


def _extract_intend(input_value: Any, name: Any) -> str:
    if isinstance(input_value, dict):
        value = input_value.get("intend")
        if isinstance(value, str) and value.strip():
            return value.strip()
        description = input_value.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
        inferred = _infer_builtin_tool_intend(str(name or "tool"), input_value)
        if inferred:
            return inferred
    label = name if isinstance(name, str) else "tool"
    return f"调用工具：{label}"


def _infer_builtin_tool_intend(name: str, input_value: dict[str, Any]) -> str | None:
    if name == "Read":
        file_path = input_value.get("file_path")
        if isinstance(file_path, str) and file_path.strip():
            return f"读取 {Path(file_path).name or file_path}。"
    if name == "LS":
        path = input_value.get("path")
        if isinstance(path, str) and path.strip():
            return f"列出 {Path(path).name or path} 下的文件。"
    if name == "Glob":
        pattern = input_value.get("pattern")
        if isinstance(pattern, str) and pattern.strip():
            return f"查找匹配 {pattern} 的文件。"
    if name == "Grep":
        pattern = input_value.get("pattern")
        if isinstance(pattern, str) and pattern.strip():
            return f"搜索 {pattern} 的出现位置。"
    if name == "Bash":
        command = input_value.get("command")
        if isinstance(command, str) and command.strip():
            first_line = command.strip().splitlines()[0]
            if len(first_line) > 80:
                first_line = first_line[:77] + "..."
            return f"执行命令：{first_line}"
    return None


def _normalize_tool_call_part(part: Part) -> Part:
    if part.get("type") == "tool_call":
        return part
    input_value = part.get("input")
    name = part.get("name") or "tool"
    normalized = dict(part)
    normalized["type"] = "tool_call"
    normalized["role"] = "assistant"
    normalized["intend"] = _extract_intend(input_value, name)
    normalized["toolUseId"] = part.get("toolUseId") or _tool_use_id_from_raw(part.get("raw"))
    normalized["status"] = part.get("status") or "pending"
    normalized["text"] = normalized["intend"]
    return normalized


def _tool_use_id_from_raw(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    tool_block = next((item for item in _content(raw) if _is_tool_use(item)), None)
    value = tool_block.get("id") if isinstance(tool_block, dict) else None
    return value if isinstance(value, str) else None


def _format_tool_result(content: Any, structured: Any) -> str:
    if isinstance(content, str) and content.strip():
        return _strip_reasoning_jsonl_lines(content)
    extracted = _extract_tool_result_text(content)
    if extracted:
        return _strip_reasoning_jsonl_lines(extracted)
    if structured is not None:
        import json

        return _strip_reasoning_jsonl_lines(json.dumps(structured, ensure_ascii=False, indent=2))
    return "Tool result"


def _strip_reasoning_jsonl_lines(text: Any) -> str:
    if not isinstance(text, str) or not text:
        return ""
    lines = text.splitlines()
    if not lines:
        return text
    kept: list[str] = []
    for line in lines:
        if _is_ignorable_reasoning_json_line(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def _is_ignorable_reasoning_json_line(line: str) -> bool:
    stripped = line.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return False
    try:
        import json

        parsed = json.loads(stripped)
    except Exception:
        return False
    if not isinstance(parsed, dict):
        return False
    subtype = parsed.get("subtype")
    if isinstance(subtype, str) and (subtype == "thinking_tokens" or subtype.endswith("_tokens")):
        return True
    return _raw_contains_only_reasoning_content(parsed)


def _extract_tool_result_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            if item.strip():
                parts.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
            continue
        nested = _extract_tool_result_text(item.get("content"))
        if nested:
            parts.append(nested)
    return "\n".join(parts)
