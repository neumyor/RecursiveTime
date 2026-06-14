from __future__ import annotations

from pathlib import Path

from harnessing_ts.agent.translate import collapse_tool_parts, merge_tool_result_part, should_merge_tool_result
from harnessing_ts.schema import Part
from harnessing_ts.state.jsonl import append_jsonl, read_jsonl, write_jsonl


class MessageLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, part: Part) -> None:
        if part.get("type") == "tool_result" and self._merge_tool_result(part):
            return
        append_jsonl(self.path, part)

    def _merge_tool_result(self, tool_result: Part) -> bool:
        parts = collapse_tool_parts(read_jsonl(self.path))
        for index in range(len(parts) - 1, -1, -1):
            candidate = parts[index]
            if should_merge_tool_result(candidate, tool_result):
                parts[index] = merge_tool_result_part(candidate, tool_result)
                write_jsonl(self.path, parts)
                return True
        return False
