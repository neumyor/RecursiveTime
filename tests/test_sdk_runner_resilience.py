from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from harnessing_ts.agent.sdk_runner import SdkRunner, SdkRunnerConfig
from harnessing_ts.state.message_log import MessageLog


def _make_runner(tmp_path, extra_args=None) -> SdkRunner:
    log = MessageLog(tmp_path / "main.jsonl")
    cfg = SdkRunnerConfig(
        cwd=tmp_path,
        system_prompt="test",
        allowed_tools=[],
        log=log,
        extra_args=extra_args,
    )
    return SdkRunner(cfg)


def test_extra_args_for_1m_context_window_have_no_leading_dashes(tmp_path) -> None:
    """Regression test: the SDK's subprocess_cli transport prepends its own
    '--' to every extra_args key. If the harness passes '--betas' the CLI
    receives '----betas', rejects the unknown option on startup, and the
    SDK then hangs for 60s before raising 'Control request timeout:
    initialize'. Keys must NOT have leading dashes."""
    from harnessing_ts.settings.llm import build_sdk_invocation_config
    from harnessing_ts.settings.llm import LlmConfig

    cfg = LlmConfig(
        authMode="manual",
        model="m",
        apiKey="k",
        baseUrl=None,
        protocol="anthropic",
        contextWindow="1m",
    )
    sdk = build_sdk_invocation_config(cfg)
    assert sdk.extra_args is not None
    for flag in sdk.extra_args.keys():
        assert not flag.startswith("-"), (
            f"extra_args key {flag!r} starts with '-'; the SDK transport "
            f"prepends its own '--', so the CLI would see '----{flag.lstrip('-')}'. "
            f"Pass the flag name without leading dashes."
        )
    assert "betas" in sdk.extra_args
    assert sdk.extra_args["betas"] == "context-1m-2025-08-07"


def test_extra_args_for_200k_context_window_is_empty(tmp_path) -> None:
    from harnessing_ts.settings.llm import build_sdk_invocation_config
    from harnessing_ts.settings.llm import LlmConfig

    cfg = LlmConfig(
        authMode="manual",
        model="m",
        apiKey="k",
        baseUrl=None,
        protocol="anthropic",
        contextWindow="200k",
    )
    sdk = build_sdk_invocation_config(cfg)
    assert sdk.extra_args in (None, {})


def test_runner_resets_client_on_connect_failure(tmp_path) -> None:
    """When ClaudeSDKClient.connect() raises (e.g. CLI crashed on startup),
    the runner must drop the cached client so the next send() spawns a
    fresh CLI subprocess instead of reusing the dead one."""
    runner = _make_runner(tmp_path)

    fake_client = AsyncMock()
    fake_client.connect.side_effect = RuntimeError("simulated CLI crash")
    # MagicMock (not AsyncMock) so calling the class is a sync function
    # returning the awaitable fake client.
    fake_client_class = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"claude_code_sdk": SimpleNamespace(
        ClaudeSDKClient=fake_client_class,
        ClaudeCodeOptions=lambda **k: SimpleNamespace(**k),
    )}):
        with patch("harnessing_ts.agent.sdk_runner.build_disallowed_tools", return_value=[]):
            raised = False
            try:
                asyncio.run(runner.send("hello"))
            except RuntimeError:
                raised = True
            assert raised, "send() should propagate the connect() error"
    assert runner._client is None, (
        "Runner should have cleared the dead client so the next send() "
        "spawns a fresh one instead of reusing it"
    )


def test_runner_resets_client_on_receive_loop_error(tmp_path) -> None:
    """If the receive_response() loop raises (e.g. SDK raises 'Control
    request timeout: initialize' because the CLI died mid-stream), the
    runner must clear the cached client."""
    runner = _make_runner(tmp_path)

    fake_client = AsyncMock()
    fake_client.connect = AsyncMock()
    fake_client.query = AsyncMock()
    fake_client.receive_response = AsyncMock(
        side_effect=Exception("Control request timeout: initialize")
    )

    fake_client_class = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"claude_code_sdk": SimpleNamespace(
        ClaudeSDKClient=fake_client_class,
        ClaudeCodeOptions=lambda **k: SimpleNamespace(**k),
    )}):
        with patch("harnessing_ts.agent.sdk_runner.build_disallowed_tools", return_value=[]):
            raised = False
            try:
                asyncio.run(runner.send("hello"))
            except Exception:
                raised = True
            assert raised
    assert runner._client is None, (
        "Runner should drop the client when the receive loop dies; "
        "otherwise the next send() reuses the dead client and hangs "
        "another 60s on the same initialize timeout"
    )


def test_runner_keeps_client_on_normal_completion(tmp_path) -> None:
    """Sanity check: a successful send() must NOT clear the client. The
    next send() should reuse it (preserves conversation context)."""
    runner = _make_runner(tmp_path)

    fake_message = SimpleNamespace(session_id="sess-1")
    async def _yield_one():
        yield fake_message
    fake_message_iter = _yield_one()

    fake_client = AsyncMock()
    fake_client.connect = AsyncMock()
    fake_client.query = AsyncMock()
    fake_client.receive_response = lambda: fake_message_iter
    fake_client_class = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"claude_code_sdk": SimpleNamespace(
        ClaudeSDKClient=fake_client_class,
        ClaudeCodeOptions=lambda **k: SimpleNamespace(**k),
    )}):
        with patch("harnessing_ts.agent.sdk_runner.build_disallowed_tools", return_value=[]):
            asyncio.run(runner.send("hello"))
    assert runner._client is fake_client, (
        "Successful send() should keep the client so subsequent sends "
        "reuse the same SDK session"
    )
