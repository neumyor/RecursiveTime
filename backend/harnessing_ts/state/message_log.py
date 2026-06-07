from __future__ import annotations

from pathlib import Path

from harnessing_ts.schema import Part
from harnessing_ts.state.jsonl import append_jsonl


class MessageLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, part: Part) -> None:
        append_jsonl(self.path, part)

