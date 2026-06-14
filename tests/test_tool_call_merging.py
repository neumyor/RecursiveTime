from __future__ import annotations

from harnessing_ts.agent.translate import collapse_tool_parts, sdk_message_to_part
from harnessing_ts.state.jsonl import read_jsonl
from harnessing_ts.state.message_log import MessageLog


def _assistant_tool_message() -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Read",
                    "input": {"file_path": "README.md", "intend": "读取 README 以确认项目说明。"},
                }
            ]
        },
    }


def _user_tool_result_message() -> dict:
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": [{"type": "text", "text": "# HarnessingTS"}],
                }
            ]
        },
        "tool_use_result": {"content": "# HarnessingTS"},
    }


def test_tool_use_and_result_collapse_to_one_tool_call_part() -> None:
    tool_call = sdk_message_to_part(_assistant_tool_message())
    tool_result = sdk_message_to_part(_user_tool_result_message())

    collapsed = collapse_tool_parts([tool_call, tool_result])

    assert len(collapsed) == 1
    assert collapsed[0]["type"] == "tool_call"
    assert collapsed[0]["status"] == "completed"
    assert collapsed[0]["intend"] == "读取 README 以确认项目说明。"
    assert collapsed[0]["resultText"] == "# HarnessingTS"


def test_message_log_merges_tool_result_into_prior_tool_call(tmp_path) -> None:
    log = MessageLog(tmp_path / "main.jsonl")
    log.append(sdk_message_to_part(_assistant_tool_message()))
    log.append(sdk_message_to_part(_user_tool_result_message()))

    parts = read_jsonl(log.path)

    assert len(parts) == 1
    assert parts[0]["type"] == "tool_call"
    assert parts[0]["status"] == "completed"
    assert parts[0]["resultText"] == "# HarnessingTS"
