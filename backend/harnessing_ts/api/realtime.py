from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True)
class RealtimeEvent:
    id: int
    type: str
    payload: dict[str, Any]

    def as_sse(self) -> str:
        body = json.dumps(
            {"id": self.id, "type": self.type, "payload": self.payload},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"id: {self.id}\ndata: {body}\n\n"


class RealtimeEventBroker:
    def __init__(self, *, queue_size: int = 64) -> None:
        self.queue_size = queue_size
        self._next_id = 1
        self._subscribers: set[asyncio.Queue[RealtimeEvent]] = set()

    def subscribe(self) -> asyncio.Queue[RealtimeEvent]:
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[RealtimeEvent]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event_type: str, payload: dict[str, Any]) -> RealtimeEvent:
        event = RealtimeEvent(self._next_id, event_type, payload)
        self._next_id += 1
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event
