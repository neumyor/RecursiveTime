from __future__ import annotations

import asyncio
from io import BytesIO
import zipfile

from harnessing_ts.agent.translate import user_text_part
from harnessing_ts.api.realtime import RealtimeEventBroker
from harnessing_ts.orchestrator import HarnessOrchestrator


def test_realtime_broker_publishes_to_all_subscribers() -> None:
    broker = RealtimeEventBroker()
    first = broker.subscribe()
    second = broker.subscribe()

    event = broker.publish("main_parts", {"mainParts": [{"id": "p1"}]})

    assert first.get_nowait() == event
    assert second.get_nowait() == event
    assert "event" not in event.as_sse()
    assert '"type":"main_parts"' in event.as_sse()


def test_realtime_broker_drops_oldest_event_for_slow_subscriber() -> None:
    broker = RealtimeEventBroker(queue_size=1)
    queue = broker.subscribe()

    broker.publish("first", {})
    latest = broker.publish("second", {})

    assert queue.get_nowait() == latest


def test_main_part_event_contains_collapsed_persisted_transcript(tmp_path) -> None:
    orchestrator = HarnessOrchestrator(tmp_path)
    orchestrator.initialize()
    events: list[tuple[str, dict]] = []
    orchestrator.set_realtime_event_sink(lambda kind, payload: events.append((kind, payload)))
    part = user_text_part("hello")
    orchestrator.store.append_main_part(part)

    orchestrator._emit_main_parts(part)

    assert events[-1][0] == "main_parts"
    assert events[-1][1]["mainParts"][0]["text"] == "hello"


def test_node_part_event_contains_session_transcript_and_state(tmp_path) -> None:
    orchestrator = HarnessOrchestrator(tmp_path)
    orchestrator.initialize()
    events: list[tuple[str, dict]] = []
    orchestrator.set_realtime_event_sink(lambda kind, payload: events.append((kind, payload)))
    node = orchestrator.store.create_node_session("problem-contract")
    part = user_text_part("execute node")
    orchestrator.store.append_node_part(node["id"], part)

    orchestrator._emit_node_parts(node["id"], part)

    assert events[-1][0] == "node_parts"
    assert events[-1][1]["nodePartsById"][node["id"]][0]["text"] == "execute node"
    assert events[-1][1]["nodes"][0]["id"] == node["id"]


def test_reference_upload_emits_realtime_file_tree(tmp_path) -> None:
    orchestrator = HarnessOrchestrator(tmp_path)
    orchestrator.initialize()
    events: list[tuple[str, dict]] = []
    orchestrator.set_realtime_event_sink(lambda kind, payload: events.append((kind, payload)))

    path = orchestrator.upload_reference_file("paper.txt", b"reference")

    assert path == "references/paper.txt"
    assert events[-1][0] == "workspace_files"
    assert events[-1][1]["change"] == {"kind": "reference_uploaded", "path": path}
    assert events[-1][1]["fileTree"]["root"] == str(tmp_path)


def test_raw_zip_upload_emits_realtime_file_tree(tmp_path) -> None:
    orchestrator = HarnessOrchestrator(tmp_path)
    orchestrator.initialize()
    events: list[tuple[str, dict]] = []
    orchestrator.set_realtime_event_sink(lambda kind, payload: events.append((kind, payload)))
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("dataset.csv", "x,y\n1,2\n")

    result = orchestrator.upload_raw_data_zip("dataset.zip", archive.getvalue())

    assert result["extracted"]
    assert events[-1][0] == "workspace_files"
    assert events[-1][1]["change"]["kind"] == "raw_data_uploaded"
    assert events[-1][1]["change"]["extractedCount"] == 1


def test_main_runner_receives_realtime_part_callback(tmp_path) -> None:
    orchestrator = HarnessOrchestrator(tmp_path)
    orchestrator.initialize()

    from unittest.mock import MagicMock, patch

    with patch("harnessing_ts.orchestrator.build_main_runner", return_value=MagicMock()) as build:
        orchestrator._ensure_main_runner()

    assert build.call_args.kwargs["on_part"] == orchestrator._emit_main_parts


def test_realtime_broker_unsubscribe_stops_delivery() -> None:
    broker = RealtimeEventBroker()
    queue = broker.subscribe()
    broker.unsubscribe(queue)

    broker.publish("main_parts", {})

    try:
        queue.get_nowait()
    except asyncio.QueueEmpty:
        pass
    else:
        raise AssertionError("Unsubscribed queue unexpectedly received an event")
