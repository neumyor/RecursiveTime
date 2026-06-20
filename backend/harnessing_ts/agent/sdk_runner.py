from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from harnessing_ts.agent.translate import merge_tool_result_part, sdk_message_to_part, should_merge_tool_result, user_text_part
from harnessing_ts.schema import Part
from harnessing_ts.state.message_log import MessageLog


@dataclass
class SdkRunnerConfig:
    cwd: Path
    system_prompt: str
    allowed_tools: list[str]
    log: MessageLog
    disallowed_tools: list[str] | None = None
    attachment_text: str | None = None
    model: str | None = None
    env: dict[str, str] | None = None
    extra_args: dict[str, Any] | None = None
    mcp_server: Any | None = None
    on_part: Callable[[Part], None] | None = None
    on_session_id: Callable[[str], None] | None = None


class SdkRunner:
    def __init__(self, config: SdkRunnerConfig) -> None:
        self.config = config
        self._pending_attachment = config.attachment_text
        self.session_id: str | None = None
        self._client: Any | None = None
        self._running = False
        self._interrupted = False

    async def send_with_user_echo(self, text: str, context_text: str | None = None) -> list[Part]:
        user_part = user_text_part(text)
        self.config.log.append(user_part)
        if self.config.on_part:
            self.config.on_part(user_part)
        query_text = f"{context_text}\n\n## Current User Message\n{text}" if context_text else text
        assistant_parts = await self.send(query_text)
        return [user_part, *assistant_parts]

    async def send(self, text: str) -> list[Part]:
        try:
            from claude_code_sdk import (
                ClaudeSDKClient,
                ClaudeCodeOptions,
            )
        except Exception as exc:
            raise RuntimeError(
                "Python Claude Code SDK is not installed. Run `uv sync` first. "
                f"Original error: {exc}"
            ) from exc

        content = f"{self._pending_attachment}\n\n{text}" if self._pending_attachment else text
        self._pending_attachment = None
        kwargs: dict[str, Any] = {
            "cwd": str(self.config.cwd),
            "system_prompt": self.config.system_prompt,
            "allowed_tools": self.config.allowed_tools,
            "disallowed_tools": self.config.disallowed_tools or build_disallowed_tools(self.config.allowed_tools),
            "max_turns": int(os.getenv("TS_HARNESS_MAX_TURNS", "80")),
            "env": self._runtime_env(),
        }
        if self.config.model:
            kwargs["model"] = self.config.model
        if self.config.extra_args:
            kwargs["extra_args"] = self.config.extra_args
        if self.config.mcp_server is not None:
            kwargs["mcp_servers"] = {"ts_harness": self.config.mcp_server}

        parts: list[Part] = []
        options = ClaudeCodeOptions(**kwargs)
        if self._client is None:
            self._client = ClaudeSDKClient(options=options)
            try:
                await self._client.connect()
            except Exception:
                # The Claude Code CLI failed to start (missing binary,
                # version mismatch, unknown extra_args option, etc.).
                # The cached client would deadlock the next send() on the
                # SDK's 60s "initialize" control-request timeout because
                # connect() never finished. Drop it so the next call
                # spawns a fresh CLI.
                self._client = None
                raise
        self._running = True
        self._interrupted = False
        try:
            await self._client.query(content)
            async for message in self._client.receive_response():
                session_id = getattr(message, "session_id", None)
                if isinstance(session_id, str) and session_id != self.session_id:
                    self.session_id = session_id
                    if self.config.on_session_id:
                        self.config.on_session_id(session_id)
                part = sdk_message_to_part(message)
                self.config.log.append(part)
                if self.config.on_part:
                    self.config.on_part(part)
                if part.get("type") == "tool_result" and _merge_returned_tool_result(parts, part):
                    continue
                parts.append(part)
        except BaseException:
            # Anything that escapes the receive loop — SDK exceptions,
            # "Control request timeout: initialize", user interrupt, or
            # BaseException-derived cancellations — leaves the client in
            # an unusable state. Clear it so the next send() spawns a
            # fresh CLI subprocess instead of hanging on the cached one.
            self._client = None
            raise
        finally:
            self._running = False
        if self._interrupted:
            raise RuntimeError("Interrupted by user.")
        return parts

    @property
    def is_running(self) -> bool:
        return self._running

    async def interrupt(self) -> None:
        self._interrupted = True
        if self._client is not None:
            try:
                await self._client.interrupt()
            except Exception:
                # Some Claude Code SDK versions can raise internal TaskGroup
                # bookkeeping errors while an interrupt is racing a response.
                # The harness treats interrupt as best-effort and still marks
                # the runner interrupted so the orchestrator can pause state.
                pass

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def _runtime_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.config.env:
            env.update(self.config.env)
        venv = self.config.cwd / ".venv"
        bin_dir = venv / "bin"
        if venv.exists():
            env["VIRTUAL_ENV"] = str(venv)
            if bin_dir.exists():
                current_path = env.get("PATH", "")
                paths = [str(bin_dir), *[item for item in current_path.split(os.pathsep) if item]]
                env["PATH"] = os.pathsep.join(dict.fromkeys(paths))
        else:
            env.pop("VIRTUAL_ENV", None)
        env["UV_PROJECT"] = str(self.config.cwd)
        return env


BUILTIN_TOOLS = {
    "Task",
    "AskUserQuestion",
    "Bash",
    "CronCreate",
    "CronDelete",
    "CronList",
    "Edit",
    "EnterPlanMode",
    "EnterWorktree",
    "ExitPlanMode",
    "ExitWorktree",
    "Glob",
    "Grep",
    "NotebookEdit",
    "Read",
    "ScheduleWakeup",
    "Skill",
    "TaskOutput",
    "TaskStop",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "Write",
}


def build_disallowed_tools(allowed_tools: list[str]) -> list[str]:
    allowed_builtin = {tool for tool in allowed_tools if not tool.startswith("mcp__")}
    return sorted(BUILTIN_TOOLS - allowed_builtin)


def _merge_returned_tool_result(parts: list[Part], tool_result: Part) -> bool:
    for index in range(len(parts) - 1, -1, -1):
        candidate = parts[index]
        if should_merge_tool_result(candidate, tool_result):
            parts[index] = merge_tool_result_part(candidate, tool_result)
            return True
    return False
