from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harnessing_ts.agent.control import extract_control, is_valid_node_type
from harnessing_ts.agent.sdk_runner import SdkRunner, SdkRunnerConfig
from harnessing_ts.agent.translate import system_text_part
from harnessing_ts.mcp.server import create_harness_mcp_server
from harnessing_ts.prompts.compose import (
    PromptContext,
    build_main_attachment,
    build_main_system_prompt,
    build_node_attachment,
    build_node_system_prompt,
)
from harnessing_ts.schema import NODE_SPECS, NodeSession, NodeType, Part, RunRecord, WorkspaceState, get_next_node
from harnessing_ts.settings.llm import build_sdk_invocation_config, read_effective_llm_config
from harnessing_ts.state.message_log import MessageLog
from harnessing_ts.state.workspace_store import WorkspaceStore, now_iso
from harnessing_ts.tools.compose_tools import build_main_allowed_tools, build_node_allowed_tools, build_node_native_tools


class HarnessOrchestrator:
    def __init__(self, workspace_path: Path, locale: str = "zh", mode: str = "manual", dry_run: bool = False) -> None:
        self.workspace_path = workspace_path
        self.locale = locale
        self.mode = mode
        self.dry_run = dry_run
        self.store = WorkspaceStore(workspace_path)
        self.state: WorkspaceState | None = None
        self.main_runner: SdkRunner | None = None
        self.active_node_runner: SdkRunner | None = None
        self.active_node_session: NodeSession | None = None

    def initialize(self) -> WorkspaceState:
        self.state = self.store.initialize(self.mode)
        return self.state

    async def send_main_user_message(self, text: str) -> list[Part]:
        self._ensure_initialized()
        assert self.state
        if self.state["activeNode"]:
            node = self._restore_active_node_session()
            if node and node.get("status") == "paused":
                return await self._resume_active_node(text, node)
            raise RuntimeError(f"Main session is locked while node {self.state['activeNode']} is active.")
        self.store.append_timeline({"type": "user_message", "timestamp": now_iso(), "message": text[:500]})
        if self.dry_run:
            part = system_text_part("\n".join([
                "Dry run mode: main session was not sent to Python Claude Code SDK.",
                "Use `start-node <nodeType>` to exercise harness state transitions without SDK.",
            ]))
            self.store.append_main_part(part)
            return [part]
        self._ensure_main_runner()
        assert self.main_runner
        parts = await self.main_runner.send_with_user_echo(text)
        await self._handle_main_control(parts)
        return parts

    async def enter_node(self, args: dict[str, Any]) -> NodeSession:
        self._ensure_initialized()
        assert self.state
        node_type = args["nodeType"]
        if self.state["activeNode"]:
            raise RuntimeError(f"Cannot enter {node_type}; active node {self.state['activeNode']} is still running.")
        node = self.store.create_node_session(node_type, args.get("rationale"), args.get("inputSummary"))
        node["status"] = "running"
        self.store.write_node_session(node)
        self.state["activeNode"] = node_type
        self.state["activeNodeSessionId"] = node["id"]
        self.store.write_state(self.state)
        self.store.append_timeline({
            "type": "node_entered",
            "timestamp": now_iso(),
            "nodeSessionId": node["id"],
            "nodeType": node_type,
            "message": args.get("rationale"),
            "payload": {"inputSummary": args.get("inputSummary")},
        })
        self.active_node_session = node
        if self.dry_run:
            self.store.append_node_part(node["id"], system_text_part(f"Dry run entered node {node_type}."))
            return node
        self._spawn_node_runner(node)
        assert self.active_node_runner
        prompt = f"请执行 {node_type} node。"
        if args.get("inputSummary"):
            prompt += f"\n\n用户/主会话补充上下文：\n{args['inputSummary']}"
        node_parts = await self.active_node_runner.send_with_user_echo(prompt)
        await self._handle_node_control(node_parts)
        await self._maybe_auto_enter_next_node(node)
        return node

    async def finish_node(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        assert self.state
        if not self.active_node_session:
            self.active_node_session = self._restore_active_node_session()
        if not self.active_node_session:
            raise RuntimeError("No active node session to finish.")
        node = self.active_node_session
        node["status"] = "completed" if args.get("success", True) else "failed"
        node["completedAt"] = now_iso()
        node["summary"] = args.get("summary", "")
        node["success"] = args.get("success", True)
        node["outputPaths"] = list(args.get("outputPaths") or [])
        self.store.write_node_session(node)

        if node["success"] and node["nodeType"] not in self.state["completedNodes"]:
            self.state["completedNodes"].append(node["nodeType"])
        self.state["activeNode"] = None
        self.state["activeNodeSessionId"] = None
        if node["nodeType"] == "problem-contract" and args.get("goalMet"):
            self.state["contractConfirmed"] = True
        if node["nodeType"] == "final-summary" and args.get("goalMet"):
            self.state["finalSummaryConfirmed"] = True
        self.store.write_state(self.state)
        self.store.append_timeline({
            "type": "node_finished",
            "timestamp": node["completedAt"],
            "nodeSessionId": node["id"],
            "nodeType": node["nodeType"],
            "message": node.get("summary"),
            "payload": {
                "success": node["success"],
                "goalMet": args.get("goalMet"),
                "outputPaths": node["outputPaths"],
            },
        })
        next_node = get_next_node(node["nodeType"])
        if self.active_node_runner:
            await self.active_node_runner.close()
        self.active_node_runner = None
        self.active_node_session = None
        return {"nodeSessionId": node["id"], "nextNode": next_node if node["success"] else None}

    def record_artifact(self, args: dict[str, Any]) -> dict[str, bool]:
        self._ensure_initialized()
        self.store.record_artifact(args["path"], self.active_node_session.get("id") if self.active_node_session else None, self.active_node_session.get("nodeType") if self.active_node_session else None, args.get("summary"))
        return {"ok": True}

    def record_run(self, args: RunRecord) -> dict[str, bool]:
        self._ensure_initialized()
        record = dict(args)
        if self.active_node_session:
            record.setdefault("nodeSessionId", self.active_node_session["id"])
            record.setdefault("nodeType", self.active_node_session["nodeType"])
        self.store.record_run(record)
        return {"ok": True}

    def request_user_decision(self, args: dict[str, Any]) -> dict[str, bool]:
        self._ensure_initialized()
        self.store.append_timeline({
            "type": "decision_request_ignored",
            "timestamp": now_iso(),
            "message": args.get("question", "Decision request ignored because human gates are disabled."),
            "payload": {"context": args.get("context")},
        })
        return {"recorded": True}

    async def interrupt_current(self, reason: str | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        assert self.state
        message = reason or "Interrupted by user."
        target = "none"
        if self.state.get("activeNodeSessionId"):
            target = "node"
            if self.active_node_runner:
                try:
                    await self.active_node_runner.interrupt()
                except Exception:
                    pass
            node = self.active_node_session or self._restore_active_node_session()
            if node:
                node["status"] = "paused"
                node["summary"] = f"Paused by user: {message}"
                self.store.write_node_session(node)
                self.store.append_node_part(node["id"], system_text_part(f"Harness pause: {message}"))
                self.store.append_timeline({
                    "type": "node_paused",
                    "timestamp": now_iso(),
                    "nodeSessionId": node["id"],
                    "nodeType": node["nodeType"],
                    "message": message,
                })
            self.store.write_state(self.state)
            self.active_node_runner = None
            self.active_node_session = node
        elif self.main_runner:
            target = "main"
            try:
                await self.main_runner.interrupt()
            except Exception:
                pass
            part = system_text_part(f"Harness interrupt: {message}")
            self.store.append_main_part(part)
            self.store.append_timeline({"type": "main_interrupted", "timestamp": now_iso(), "message": message})
        else:
            self.store.append_timeline({"type": "interrupt_ignored", "timestamp": now_iso(), "message": "No active runner."})
        return {"target": target, "state": self.get_state()}

    async def _resume_active_node(self, text: str, node: NodeSession) -> list[Part]:
        assert self.state
        node["status"] = "running"
        node["summary"] = "Resumed with user guidance."
        self.store.write_node_session(node)
        self.active_node_session = node
        self.store.append_timeline({
            "type": "node_resumed",
            "timestamp": now_iso(),
            "nodeSessionId": node["id"],
            "nodeType": node["nodeType"],
            "message": text[:500],
        })
        if self.dry_run:
            part = system_text_part("Dry run mode: paused node received resume guidance.")
            self.store.append_node_part(node["id"], part)
            return [part]
        self._spawn_node_runner(node)
        assert self.active_node_runner
        prompt = "\n".join([
            f"请继续执行 {node['nodeType']} node。此前节点被用户暂时中断，现在用户补充了以下说明：",
            "",
            text,
            "",
            "请结合已有 workspace 文件、节点日志和这条补充说明继续推进当前 node。不要重新开始整个 pipeline，除非用户明确要求。",
        ])
        parts = await self.active_node_runner.send_with_user_echo(prompt)
        await self._handle_node_control(parts)
        await self._maybe_auto_enter_next_node(node)
        return parts

    def get_state(self) -> WorkspaceState:
        self._ensure_initialized()
        disk_state = self.store.read_state()
        if disk_state:
            self.state = disk_state
        assert self.state
        return self.state

    def get_timeline(self) -> list[dict[str, Any]]:
        self._ensure_initialized()
        return self.store.read_timeline()

    def get_main_parts(self) -> list[Part]:
        self._ensure_initialized()
        return self.store.read_main_parts()

    def get_node_sessions(self) -> list[NodeSession]:
        self._ensure_initialized()
        return self.store.list_node_sessions()

    def get_node_parts(self, node_session_id: str) -> list[Part]:
        self._ensure_initialized()
        return self.store.read_node_parts(node_session_id)

    def get_node_parts_by_id(self, limit_per_node: int = 1000) -> dict[str, list[Part]]:
        self._ensure_initialized()
        out: dict[str, list[Part]] = {}
        for node in self.get_node_sessions():
            parts = self.store.read_node_parts(node["id"])
            out[node["id"]] = parts[-limit_per_node:]
        return out

    def get_file_tree(self) -> dict[str, Any]:
        self._ensure_initialized()
        return self.store.list_file_tree()

    def get_runtime_status(self) -> dict[str, Any] | None:
        self._ensure_initialized()
        return self.store.read_runtime_status()

    def read_workspace_file(self, path: str) -> dict[str, Any]:
        self._ensure_initialized()
        return self.store.read_text_file(path)

    def upload_reference_file(self, filename: str, content: bytes) -> str:
        self._ensure_initialized()
        return self.store.write_reference_file(filename, content)

    def clear_debug_logs(self, scope: str = "main") -> None:
        self._ensure_initialized()
        self.store.clear_debug_logs("all" if scope == "all" else "main")
        if scope == "all":
            self.state = self.store.read_state()
            self.active_node_session = None
            self.active_node_runner = None
            self.store.append_timeline({"type": "state_updated", "timestamp": now_iso(), "message": "Debug logs cleared", "payload": {"scope": scope}})

    def get_node_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": spec.type,
                "phase": spec.phase,
                "purpose": spec.purpose,
                "requires": list(spec.requires),
                "produces": list(spec.produces),
                "next": spec.next,
                "nativeTools": build_node_native_tools(spec.type),
            }
            for spec in NODE_SPECS
        ]

    async def close(self) -> None:
        if self.main_runner:
            await self.main_runner.close()
        if self.active_node_runner:
            await self.active_node_runner.close()

    async def _handle_main_control(self, parts: list[Part]) -> None:
        control = extract_control(parts)
        if not control:
            return
        action = control.get("action")
        if action == "enter_node":
            node_type = control.get("nodeType")
            if not is_valid_node_type(node_type):
                self.store.append_timeline({
                    "type": "error",
                    "timestamp": now_iso(),
                    "message": "Invalid harnessControl enter_node nodeType",
                    "payload": control,
                })
                return
            if self.state and self.state.get("activeNode"):
                return
            part = system_text_part(f"Harness control: starting node {node_type}.")
            self.store.append_main_part(part)
            try:
                await self.enter_node({
                    "nodeType": node_type,
                    "rationale": str(control.get("rationale") or f"Agent requested {node_type}"),
                    "inputSummary": str(control.get("inputSummary") or "") or None,
                })
            except RuntimeError:
                return
            return
        if action == "request_user_decision":
            self.store.append_timeline({
                "type": "decision_request_ignored",
                "timestamp": now_iso(),
                "message": "Human confirmation gates are disabled; continuing pipeline without waiting.",
                "payload": control,
            })

    async def _handle_node_control(self, parts: list[Part]) -> None:
        control = extract_control(parts)
        if not control:
            fallback = self._infer_finish_from_artifacts()
            if fallback:
                self.store.append_timeline({
                    "type": "node_control_inferred",
                    "timestamp": now_iso(),
                    "nodeSessionId": self.active_node_session.get("id") if self.active_node_session else None,
                    "nodeType": self.active_node_session.get("nodeType") if self.active_node_session else None,
                    "message": "Node finish inferred from required artifacts because harnessControl JSON was missing or malformed.",
                    "payload": fallback,
                })
                await self.finish_node(fallback)
                return
            self.store.append_timeline({
                "type": "node_protocol_error",
                "timestamp": now_iso(),
                "nodeSessionId": self.active_node_session.get("id") if self.active_node_session else None,
                "nodeType": self.active_node_session.get("nodeType") if self.active_node_session else None,
                "message": "Node response did not include finish_node harnessControl; pipeline stopped without human gate.",
            })
            await self.finish_node({
                "success": False,
                "summary": "Node response did not include finish_node harnessControl.",
                "goalMet": False,
                "outputPaths": [],
            })
            return
        if control.get("action") != "finish_node":
            return
        await self.finish_node({
            "success": bool(control.get("success", True)),
            "summary": str(control.get("summary") or "Node finished via harnessControl."),
            "goalMet": control.get("goalMet"),
            "outputPaths": [str(item) for item in control.get("outputPaths", []) if item],
        })

    def _infer_finish_from_artifacts(self) -> dict[str, Any] | None:
        node = self.active_node_session
        if not node:
            return None
        node_type = node["nodeType"]
        if node_type == "problem-contract":
            required = ["user/problem-contract.md", "user/data-spec.md"]
            if all((self.workspace_path / path).exists() for path in required):
                return {
                    "success": True,
                    "summary": "Finished problem-contract; inferred from user/problem-contract.md and user/data-spec.md.",
                    "goalMet": False,
                    "outputPaths": required,
                }
            return None
        if node_type == "iterative-solving":
            state_path = self.workspace_path / "user" / "iteration-state.md"
            reports_dir = self.workspace_path / "reports" / "iterations"
            if state_path.exists() and reports_dir.exists() and any(reports_dir.glob("*-summary.md")):
                return {
                    "success": True,
                    "summary": "Finished iterative-solving; inferred from iteration-state and iteration summary artifacts.",
                    "goalMet": False,
                    "outputPaths": ["user/iteration-state.md", "reports/iterations/**"],
                }
            return None
        if node_type == "final-summary":
            required = ["reports/final-summary.md", "user/final-solution.md"]
            if all((self.workspace_path / path).exists() for path in required):
                return {
                    "success": True,
                    "summary": "Finished final-summary; inferred from final summary artifacts.",
                    "goalMet": True,
                    "outputPaths": required,
                }
        return None

    async def _maybe_auto_enter_next_node(self, finished_node: NodeSession) -> None:
        self._ensure_initialized()
        assert self.state
        latest = self.store.read_node_session(finished_node["id"]) or finished_node
        if self.state.get("activeNode") or latest.get("status") != "completed" or latest.get("success") is not True:
            return
        next_node = self._next_node_after_completion(latest)
        if not next_node:
            return
        self.store.append_timeline({
            "type": "auto_next",
            "timestamp": now_iso(),
            "nodeSessionId": latest["id"],
            "nodeType": latest["nodeType"],
            "message": f"Auto-entering {next_node}.",
            "payload": {"nextNode": next_node},
        })
        await self.enter_node({
            "nodeType": next_node,
            "rationale": f"Previous node {latest['nodeType']} completed successfully; continuing node chain.",
            "inputSummary": f"Upstream node {latest['nodeType']} completed. Summary: {latest.get('summary', '')}. Output paths: {', '.join(latest.get('outputPaths', []))}",
        })

    def _next_node_after_completion(self, latest: NodeSession) -> NodeType | None:
        if latest["nodeType"] == "iterative-solving" and self._iteration_recommends_continue():
            return "iterative-solving"
        return get_next_node(latest["nodeType"])

    def _iteration_recommends_continue(self) -> bool:
        state_file = self.workspace_path / "user" / "iteration-state.md"
        try:
            text = state_file.read_text(encoding="utf-8").lower()
        except FileNotFoundError:
            return False
        false_markers = (
            "recommend_exit: false",
            "recommend_exit=false",
            "recommend exit: false",
            "recommend exit=false",
            "建议退出: false",
            "建议退出：false",
        )
        true_markers = (
            "recommend_exit: true",
            "recommend_exit=true",
            "recommend exit: true",
            "recommend exit=true",
            "建议退出: true",
            "建议退出：true",
        )
        if any(marker in text for marker in false_markers):
            return True
        if any(marker in text for marker in true_markers):
            return False
        return False

    def _ensure_initialized(self) -> None:
        if not self.state:
            self.initialize()

    def _restore_active_node_session(self) -> NodeSession | None:
        if not self.state or not self.state.get("activeNodeSessionId"):
            return None
        return self.store.read_node_session(self.state["activeNodeSessionId"])

    def _ensure_main_runner(self) -> None:
        if self.main_runner:
            return
        ctx = PromptContext(str(self.workspace_path), self.locale)
        llm_config = read_effective_llm_config(self.workspace_path)
        sdk_config = build_sdk_invocation_config(llm_config)
        mcp_server = None if self._should_disable_mcp(llm_config) else create_harness_mcp_server(
            session_role="main",
            enter_node=self.enter_node,
        )
        self.main_runner = SdkRunner(SdkRunnerConfig(
            cwd=self.workspace_path,
            system_prompt=build_main_system_prompt(ctx),
            attachment_text=build_main_attachment(ctx),
            allowed_tools=build_main_allowed_tools(),
            model=sdk_config.model,
            env=sdk_config.env,
            extra_args=sdk_config.extra_args,
            mcp_server=mcp_server,
            log=MessageLog(self.store.main_log_path),
        ))

    def _spawn_node_runner(self, node: NodeSession) -> None:
        ctx = PromptContext(str(self.workspace_path), self.locale)
        llm_config = read_effective_llm_config(self.workspace_path)
        sdk_config = build_sdk_invocation_config(llm_config)
        mcp_server = None if self._should_disable_mcp(llm_config) else create_harness_mcp_server(
            session_role="node",
            finish_node=self.finish_node,
            record_artifact=self.record_artifact,
            record_run=self.record_run,
        )

        def on_session_id(sdk_session_id: str) -> None:
            node["sdkSessionId"] = sdk_session_id
            self.store.write_node_session(node)

        self.active_node_runner = SdkRunner(SdkRunnerConfig(
            cwd=self.workspace_path,
            system_prompt=build_node_system_prompt(node["nodeType"], ctx),
            attachment_text=build_node_attachment(node["nodeType"], node.get("inputSummary")),
            allowed_tools=build_node_allowed_tools(node["nodeType"]),
            model=sdk_config.model,
            env=sdk_config.env,
            extra_args=sdk_config.extra_args,
            mcp_server=mcp_server,
            log=MessageLog(self.store.node_log_path(node["id"])),
            on_session_id=on_session_id,
        ))

    def _should_disable_mcp(self, llm_config: Any) -> bool:
        if os.getenv("TS_HARNESS_ENABLE_MCP") == "true":
            return False
        if os.getenv("TS_HARNESS_DISABLE_MCP") == "true":
            return True
        return llm_config.authMode == "manual" and bool(llm_config.baseUrl)
