from __future__ import annotations

import json
import re
from typing import Any

from harnessing_ts.schema import NODE_TYPES, Part

CONTROL_KEY = "harnessControl"
_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
_INLINE_RE = re.compile(r"\{[\s\S]*?\"harnessControl\"[\s\S]*?\}\s*$")
_DSML_LINE_RE = re.compile(r"^.*DSML.*$", re.MULTILINE)


def extract_control(parts: list[Part]) -> dict[str, Any] | None:
    for part in reversed(parts):
        text = part.get("text", "")
        if part.get("role") != "assistant" or not text:
            continue
        control = extract_control_from_text(text)
        if control:
            return control
    return None


def extract_control_from_text(text: str) -> dict[str, Any] | None:
    candidates = [match.group(1) for match in _FENCE_RE.finditer(text)]
    inline = _INLINE_RE.search(text)
    if inline:
        candidates.append(inline.group(0))
    cleaned = _DSML_LINE_RE.sub("", text)
    candidates.extend(_balanced_json_objects(cleaned))
    for candidate in reversed(candidates):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        control = payload.get(CONTROL_KEY) if isinstance(payload, dict) else None
        if isinstance(control, dict):
            return _normalize_control(control)
    return None


def strip_control_blocks(text: str) -> str:
    text = _FENCE_RE.sub(lambda match: "" if CONTROL_KEY in match.group(1) else match.group(0), text)
    text = _DSML_LINE_RE.sub("", text)
    return _INLINE_RE.sub("", text).strip()


def _balanced_json_objects(text: str) -> list[str]:
    objects: list[str] = []
    starts = [index for index, char in enumerate(text) if char == "{"]
    for start in starts:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : index + 1]
                    if CONTROL_KEY in candidate:
                        objects.append(candidate)
                    break
    return objects


def _normalize_control(control: dict[str, Any]) -> dict[str, Any] | None:
    action = control.get("action")
    if not isinstance(action, str):
        return None
    normalized = dict(control)
    normalized["action"] = action.replace("-", "_")
    node_type = normalized.get("nodeType") or normalized.get("node_type")
    if isinstance(node_type, str):
        normalized["nodeType"] = node_type
    return normalized


def is_valid_node_type(value: Any) -> bool:
    return isinstance(value, str) and value in NODE_TYPES
