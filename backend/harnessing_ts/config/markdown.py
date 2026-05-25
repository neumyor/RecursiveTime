from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Any


CONFIG_DIR = Path(__file__).resolve().parent
NODES_DIR = CONFIG_DIR / "nodes"


def read_config_text(name: str) -> str:
    return (CONFIG_DIR / name).read_text(encoding="utf-8")


def read_prompt_text(relative_path: str) -> str:
    return (CONFIG_DIR / "prompts" / relative_path).read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def node_documents() -> list[dict[str, Any]]:
    by_type = {path.name: _read_node_document(path) for path in NODES_DIR.iterdir() if path.is_dir()}
    return _order_node_documents(by_type)


def node_document(node_type: str) -> dict[str, Any]:
    for item in node_documents():
        if item["type"] == node_type:
            return item
    raise RuntimeError(f"Missing node config directory: config/nodes/{node_type}")


def _read_node_document(path: Path) -> dict[str, Any]:
    fields = _parse_spec_file(path / "spec.md")
    fields["type"] = path.name
    fields["guidance"] = (path / "guidance.md").read_text(encoding="utf-8").strip()
    fields["native_tools"] = _parse_list_file(path / "native-tools.md")
    return fields


def _parse_spec_file(path: Path) -> dict[str, Any]:
    fields: dict[str, Any] = {"requires": [], "produces": []}
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        index += 1
        if not stripped:
            continue
        if stripped in {"requires:", "produces:"}:
            values, index = _parse_list(lines, index)
            fields[stripped.removesuffix(":")] = values
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            fields[key.strip()] = value.strip()

    required = ["phase", "purpose", "requires", "produces"]
    missing = [key for key in required if key not in fields or fields[key] is None or fields[key] == ""]
    if missing:
        raise RuntimeError(f"{path} is missing fields: {', '.join(missing)}")
    if fields.get("next") == "none":
        fields["next"] = None
    return fields


def _parse_list(lines: list[str], index: int) -> tuple[list[str], int]:
    values: list[str] = []
    while index < len(lines):
        item = lines[index].strip()
        if not item:
            index += 1
            if values:
                break
            continue
        if item.endswith(":") or re.match(r"^[A-Za-z_]+:\s+", item):
            break
        if item.startswith("- "):
            values.append(item[2:].strip())
            index += 1
            continue
        break
    return values, index


def _parse_list_file(path: Path) -> list[str]:
    return [line[2:].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip().startswith("- ")]


def _order_node_documents(by_type: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    referenced = {item["next"] for item in by_type.values() if item.get("next")}
    roots = [node_type for node_type in by_type if node_type not in referenced]
    if len(roots) != 1:
        raise RuntimeError(f"Expected exactly one node-chain root in config/nodes, found: {roots}")
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    current: str | None = roots[0]
    while current:
        if current in seen:
            raise RuntimeError(f"Cycle in node chain at {current}")
        try:
            item = by_type[current]
        except KeyError as exc:
            raise RuntimeError(f"Node chain references missing node config: {current}") from exc
        ordered.append(item)
        seen.add(current)
        current = item.get("next")
    missing = set(by_type) - seen
    if missing:
        raise RuntimeError(f"Node config contains unreachable nodes: {sorted(missing)}")
    return ordered
