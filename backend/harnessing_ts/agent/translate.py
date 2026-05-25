from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
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
            return {
                "id": str(uuid4()),
                "timestamp": timestamp,
                "role": "assistant",
                "type": "tool_use",
                "name": tool_use.get("name", "tool"),
                "input": tool_use.get("input"),
                "text": _format_tool_use(tool_use.get("name"), tool_use.get("input")),
                "raw": raw,
            }
        return {"id": str(uuid4()), "timestamp": timestamp, "role": "assistant", "type": "text", "text": _extract_visible_text(raw), "raw": raw}

    if msg_type == "result":
        return {"id": str(uuid4()), "timestamp": timestamp, "role": "system", "type": "result", "text": _extract_result_text(raw), "raw": raw}

    if msg_type == "user":
        tool_result = next((item for item in _content(raw) if _is_tool_result(item)), None)
        if tool_result:
            return {
                "id": str(uuid4()),
                "timestamp": timestamp,
                "role": "tool",
                "type": "tool_result",
                "text": _format_tool_result(tool_result.get("content"), raw.get("tool_use_result")),
                "raw": raw,
            }
        return {"id": str(uuid4()), "timestamp": timestamp, "role": "user", "type": "text", "text": _extract_visible_text(raw), "raw": raw}

    return {"id": str(uuid4()), "timestamp": timestamp, "role": "system", "type": "raw", "text": str(raw.get("subtype") or msg_type or ""), "raw": raw}


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


def _format_tool_result(content: Any, structured: Any) -> str:
    if isinstance(content, str) and content.strip():
        return content
    if structured is not None:
        import json

        return json.dumps(structured, ensure_ascii=False, indent=2)
    return "Tool result"
