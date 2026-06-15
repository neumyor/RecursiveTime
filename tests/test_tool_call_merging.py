from __future__ import annotations

from harnessing_ts.agent.translate import collapse_tool_parts, filter_display_parts, sdk_message_to_part
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


def _assistant_builtin_read_message_without_intend() -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_read",
                    "name": "Read",
                    "input": {"file_path": "/tmp/workspace/user/problem-contract.md"},
                }
            ]
        },
    }


def _assistant_builtin_bash_message_with_description() -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_bash",
                    "name": "Bash",
                    "input": {
                        "command": "uv run python explore.py",
                        "description": "运行数据探索脚本以生成 contract 证据。",
                    },
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


def test_builtin_tool_call_without_intend_gets_useful_inferred_title() -> None:
    part = sdk_message_to_part(_assistant_builtin_read_message_without_intend())

    assert part["type"] == "tool_call"
    assert part["intend"] == "读取 problem-contract.md。"
    assert part["input"]["file_path"].endswith("problem-contract.md")


def test_builtin_tool_call_prefers_description_as_intend() -> None:
    part = sdk_message_to_part(_assistant_builtin_bash_message_with_description())

    assert part["type"] == "tool_call"
    assert part["intend"] == "运行数据探索脚本以生成 contract 证据。"
    assert part["input"]["command"] == "uv run python explore.py"


def test_message_log_merges_tool_result_into_prior_tool_call(tmp_path) -> None:
    log = MessageLog(tmp_path / "main.jsonl")
    log.append(sdk_message_to_part(_assistant_tool_message()))
    log.append(sdk_message_to_part(_user_tool_result_message()))

    parts = read_jsonl(log.path)

    assert len(parts) == 1
    assert parts[0]["type"] == "tool_call"
    assert parts[0]["status"] == "completed"
    assert parts[0]["resultText"] == "# HarnessingTS"


def test_display_filter_hides_sdk_token_telemetry() -> None:
    useful_retry = {
        "role": "system",
        "type": "raw",
        "text": "api_retry",
        "raw": {"subtype": "api_retry", "attempt": 1, "max_retries": 3},
    }
    visible_text = {"role": "assistant", "type": "text", "text": "Builder trace output"}

    parts = filter_display_parts([
        {"role": "system", "type": "raw", "text": "thinking_tokens", "raw": {"subtype": "thinking_tokens"}},
        {"role": "system", "type": "raw", "text": "cache_creation_input_tokens", "raw": {"subtype": "cache_creation_input_tokens"}},
        {"role": "system", "type": "raw", "text": "init", "raw": {"subtype": "init"}},
        useful_retry,
        visible_text,
        {"role": "system", "type": "result", "text": "success", "raw": {"is_error": False}},
    ])

    assert parts == [useful_retry, visible_text]
