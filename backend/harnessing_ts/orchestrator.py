from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from harnessing_ts.agent.sdk_runner import SdkRunner, SdkRunnerConfig
from harnessing_ts.agent.translate import system_text_part
from harnessing_ts.knowledge_graph import (
    answer_knowledge_query,
    build_knowledge_graph,
    get_neighbors,
    get_supporting_evidence,
    search_evidence_notes,
    search_graph,
    search_knowledge_notes,
    suggest_next_checks,
)
from harnessing_ts.mcp.server import create_harness_mcp_server
from harnessing_ts.prompts.compose import (
    PromptContext,
    build_main_attachment,
    build_main_system_prompt,
    build_node_attachment,
    build_node_system_prompt,
)
from harnessing_ts.schema import NODE_SPECS, ControlRequest, NodeSession, NodeType, Part, RunRecord, WorkspaceState, get_next_node
from harnessing_ts.settings.llm import LlmConfig, build_sdk_invocation_config, mask_llm_config, read_effective_llm_config
from harnessing_ts.state.message_log import MessageLog
from harnessing_ts.state.workspace_store import WorkspaceStore, now_iso
from harnessing_ts.tools.compose_tools import build_main_allowed_tools, build_node_allowed_tools, build_node_native_tools


NODE_SPECS_BY_TYPE = {spec.type: spec for spec in NODE_SPECS}


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
        return parts

    async def request_enter_node(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        assert self.state
        if self._control_mode() == "manual":
            return self._park_control_request("enter_node", args)
        node = await self.enter_node(args)
        return {"status": "allowed", "nodeSessionId": node["id"], "nodeType": node["nodeType"]}

    async def request_finish_node(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        assert self.state
        node = self.active_node_session or self._restore_active_node_session()
        if self._control_mode() == "manual":
            result = self._park_control_request("finish_node", args, node)
            if node:
                node["status"] = "waiting_approval"
                node["summary"] = "Waiting for human approval to finish this node."
                self.store.write_node_session(node)
            return result
        return await self.finish_node(args)

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
        await self._handle_node_runner_return(node)
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
        node["goalMet"] = args.get("goalMet")
        node["nextNode"] = self._normalize_next_node(args.get("nextNode"))
        node["loopDecision"] = self._normalize_loop_decision(args.get("loopDecision"))
        self._validate_finish_control(node["nodeType"], node["success"], node.get("nextNode"), node.get("loopDecision"))
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
                "nextNode": node.get("nextNode"),
                "loopDecision": node.get("loopDecision"),
                "outputPaths": node["outputPaths"],
            },
        })
        self.active_node_runner = None
        self.active_node_session = None
        next_node = self._next_node_after_completion(node) if node["success"] else None
        return {"nodeSessionId": node["id"], "nextNode": next_node}

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

    async def request_query_knowledge(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self.query_knowledge(
            question=str(args.get("question", "")),
            domain=args.get("domain"),
            context=args.get("context") if isinstance(args.get("context"), dict) else None,
            observations=args.get("observations") if isinstance(args.get("observations"), list) else None,
        )

    async def interrupt_current(self, reason: str | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        assert self.state
        message = reason or "Interrupted by user."
        target = "none"
        node_runner_active = bool(self.active_node_runner and self.active_node_runner.is_running)
        main_runner_active = bool(self.main_runner and self.main_runner.is_running)
        has_active_node = bool(self.state.get("activeNodeSessionId"))

        if node_runner_active or (has_active_node and not main_runner_active):
            target = "node"
            if node_runner_active and self.active_node_runner:
                try:
                    await self.active_node_runner.interrupt()
                except Exception:
                    pass
            if main_runner_active and self.main_runner:
                try:
                    await self.main_runner.interrupt()
                except Exception:
                    pass
                self.store.append_timeline({
                    "type": "main_interrupted",
                    "timestamp": now_iso(),
                    "message": "Main runner interrupted while pausing active node.",
                    "payload": {"reason": message},
                })
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
        elif main_runner_active and self.main_runner:
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
        await self._handle_node_runner_return(node)
        return parts

    async def approve_pending_control(self) -> dict[str, Any]:
        self._ensure_initialized()
        assert self.state
        request = self.store.clear_pending_control()
        self.state = self.store.read_state()
        if not request:
            return {"approved": False, "message": "No pending control request.", "state": self.get_state()}
        self.store.append_timeline({
            "type": "control_approved",
            "timestamp": now_iso(),
            "nodeSessionId": request.get("nodeSessionId"),
            "nodeType": request.get("nodeType"),
            "message": request.get("message") or request["kind"],
            "payload": request,
        })
        if request["kind"] == "enter_node":
            result = await self.enter_node(request["args"])
            return {"approved": True, "result": result, "state": self.get_state()}
        if request["kind"] == "finish_node":
            result = await self.finish_node(request["args"])
            if result.get("nextNode"):
                self._park_control_request("enter_node", {
                    "nodeType": result["nextNode"],
                    "rationale": f"Previous node finished and pipeline is ready for {result['nextNode']}.",
                    "inputSummary": "Approve this control request to continue the node chain.",
                })
            return {"approved": True, "result": result, "state": self.get_state()}
        raise RuntimeError(f"Unknown control request kind: {request['kind']}")

    def reject_pending_control(self, reason: str | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        assert self.state
        request = self.store.clear_pending_control()
        self.state = self.store.read_state()
        if not request:
            return {"rejected": False, "message": "No pending control request.", "state": self.get_state()}
        message = reason or "Rejected by human."
        self.store.append_timeline({
            "type": "control_rejected",
            "timestamp": now_iso(),
            "nodeSessionId": request.get("nodeSessionId"),
            "nodeType": request.get("nodeType"),
            "message": message,
            "payload": request,
        })
        if request["kind"] == "finish_node" and request.get("nodeSessionId"):
            node = self.store.read_node_session(request["nodeSessionId"])
            if node and node.get("status") == "waiting_approval":
                node["status"] = "paused"
                node["summary"] = f"Finish request rejected: {message}"
                self.store.write_node_session(node)
                self.store.append_node_part(node["id"], system_text_part(f"Harness control rejected finish_node: {message}"))
        return {"rejected": True, "state": self.get_state()}

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

    def get_runtime_settings(self) -> dict[str, Any]:
        self._ensure_initialized()
        return self.store.read_runtime_settings()

    def update_runtime_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        updated = self.store.write_runtime_settings(settings)
        self.state = self.store.read_state()
        return updated

    def get_knowledge_graph(self) -> dict[str, Any]:
        self._ensure_initialized()
        return self.store.read_knowledge_graph()

    def get_knowledge_base_summary(self) -> dict[str, Any]:
        self._ensure_initialized()
        return self.store.read_knowledge_base_summary()

    def get_knowledge_base_cards(self, kind: str, limit: int = 200) -> dict[str, Any]:
        self._ensure_initialized()
        return self.store.read_knowledge_base_cards(kind, limit)

    def get_knowledge_graph_build_status(self) -> dict[str, Any]:
        self._ensure_initialized()
        return self.store.read_knowledge_graph_build_status()

    def get_knowledge_graph_parts(self) -> list[Part]:
        self._ensure_initialized()
        return self.store.read_knowledge_graph_parts()

    def get_knowledge_graph_llm_config(self) -> dict[str, Any]:
        self._ensure_initialized()
        cfg = self._knowledge_graph_llm_config()
        return {"config": mask_llm_config(cfg), "sdk": {}}

    async def query_knowledge(
        self,
        question: str,
        domain: str | None = None,
        context: dict[str, Any] | None = None,
        observations: list[str] | None = None,
    ) -> dict[str, Any]:
        self._ensure_initialized()
        result = await answer_knowledge_query(
            workspace_path=self.workspace_path,
            store=self.store,
            llm_config=self._knowledge_graph_llm_config(),
            question=question,
            domain=domain,
            context=context,
            observations=observations,
        )
        self.store.append_timeline({
            "type": "knowledge_query_answered",
            "timestamp": now_iso(),
            "message": question[:240],
            "payload": {
                "domain": domain,
                "supportingKnowledge": result.get("supporting_knowledge", []),
                "supportingEvidence": result.get("supporting_evidence", []),
            },
        })
        return result

    def search_knowledge_notes(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        self._ensure_initialized()
        return search_knowledge_notes(self.workspace_path, query, top_k)

    def search_evidence_notes(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        self._ensure_initialized()
        return search_evidence_notes(self.workspace_path, query, top_k)

    def search_knowledge_graph(self, query: str, relation_type: str | None = None, top_k: int = 10) -> list[dict[str, Any]]:
        self._ensure_initialized()
        return search_graph(self.workspace_path, query, relation_type, top_k)

    def get_knowledge_neighbors(self, concept: str, depth: int = 1) -> dict[str, Any]:
        self._ensure_initialized()
        return get_neighbors(self.workspace_path, concept, depth)

    def get_knowledge_supporting_evidence(self, note_or_edge_id: str, top_k: int = 8) -> list[dict[str, Any]]:
        self._ensure_initialized()
        return get_supporting_evidence(self.workspace_path, note_or_edge_id, top_k)

    def suggest_knowledge_next_checks(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        self._ensure_initialized()
        return suggest_next_checks(self.workspace_path, query, top_k)

    def update_knowledge_graph_llm_config(self, values: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        self.store.write_knowledge_graph_llm_config(values)
        cfg = self._knowledge_graph_llm_config()
        return {"config": mask_llm_config(cfg), "sdk": {}}

    async def build_knowledge_graph(self, trigger: str = "manual", uploaded_paths: list[str] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        setattr(self, "_knowledge_graph_pause_requested", False)
        status = self.store.write_knowledge_graph_build_status({
            "running": True,
            "status": "running",
            "startedAt": now_iso(),
            "finishedAt": None,
            "trigger": trigger,
            "message": "Knowledge graph build is running.",
            "uploadedPaths": uploaded_paths or [],
        })
        self.store.append_timeline({
            "type": "knowledge_graph_build_started",
            "timestamp": status["startedAt"],
            "message": trigger,
            "payload": {"uploadedPaths": uploaded_paths or []},
        })
        try:
            await build_knowledge_graph(
                workspace_path=self.workspace_path,
                store=self.store,
                llm_config=self._knowledge_graph_llm_config(),
                trigger=trigger,
                uploaded_paths=uploaded_paths,
                on_runner=lambda runner: setattr(self, "_knowledge_graph_runner", runner),
            )
        except Exception as exc:
            finished = now_iso()
            if getattr(self, "_knowledge_graph_pause_requested", False):
                self.store.write_knowledge_graph_build_status({
                    "running": False,
                    "status": "paused",
                    "finishedAt": finished,
                    "message": "Knowledge graph builder paused.",
                })
                self.store.append_timeline({
                    "type": "knowledge_graph_build_paused",
                    "timestamp": finished,
                    "message": "paused",
                    "payload": {"trigger": trigger},
                })
                return {"ok": False, "paused": True, "knowledgeGraph": self.get_knowledge_graph(), "status": self.get_knowledge_graph_build_status()}
            self.store.write_knowledge_graph_build_status({
                "running": False,
                "status": "failed",
                "finishedAt": finished,
                "message": str(exc),
            })
            self.store.append_timeline({
                "type": "knowledge_graph_build_failed",
                "timestamp": finished,
                "message": str(exc),
                "payload": {"trigger": trigger},
            })
            raise
        finished = now_iso()
        if getattr(self, "_knowledge_graph_pause_requested", False):
            self.store.write_knowledge_graph_build_status({
                "running": False,
                "status": "paused",
                "finishedAt": finished,
                "message": "Knowledge graph builder paused.",
            })
            self.store.append_timeline({
                "type": "knowledge_graph_build_paused",
                "timestamp": finished,
                "message": "paused",
                "payload": {"trigger": trigger},
            })
            return {"ok": False, "paused": True, "knowledgeGraph": self.get_knowledge_graph(), "status": self.get_knowledge_graph_build_status()}
        self.store.write_knowledge_graph_build_status({
            "running": False,
            "status": "completed",
            "finishedAt": finished,
            "message": "Knowledge graph updated.",
        })
        self.store.append_timeline({
            "type": "knowledge_graph_build_completed",
            "timestamp": finished,
            "message": "knowledge_base",
            "payload": {"trigger": trigger},
        })
        return {"ok": True, "knowledgeGraph": self.get_knowledge_graph(), "status": self.get_knowledge_graph_build_status()}

    async def pause_knowledge_graph_build(self, reason: str | None = None) -> dict[str, Any]:
        message = reason or "Paused from knowledge graph UI."
        setattr(self, "_knowledge_graph_pause_requested", True)
        runner = getattr(self, "_knowledge_graph_runner", None)
        if runner is not None:
            await runner.interrupt()
            status = self.store.write_knowledge_graph_build_status({
                "status": "pausing",
                "message": message,
            })
            self.store.append_timeline({
                "type": "knowledge_graph_build_pausing",
                "timestamp": now_iso(),
                "message": message,
            })
            return {"paused": True, "status": status}
        status = self.store.write_knowledge_graph_build_status({
            "running": False,
            "status": "paused",
            "finishedAt": now_iso(),
            "message": message,
        })
        self.store.append_timeline({
            "type": "knowledge_graph_build_paused",
            "timestamp": status["finishedAt"],
            "message": message,
        })
        return {"paused": True, "status": status}

    def read_workspace_file(self, path: str) -> dict[str, Any]:
        self._ensure_initialized()
        return self.store.read_text_file(path)

    def upload_reference_file(self, filename: str, content: bytes) -> str:
        self._ensure_initialized()
        return self.store.write_reference_file(filename, content)

    def upload_raw_data_zip(self, filename: str, content: bytes) -> dict[str, Any]:
        self._ensure_initialized()
        return self.store.extract_raw_data_zip(filename, content)

    def clear_debug_logs(self, scope: str = "main") -> None:
        self._ensure_initialized()
        self.store.clear_debug_logs("all" if scope == "all" else "main")
        if scope == "all":
            self.state = self.store.read_state()
            self.active_node_session = None
            self.active_node_runner = None

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

    def _control_mode(self) -> str:
        self._ensure_initialized()
        assert self.state
        return "auto" if self.state.get("controlMode") == "auto" else "manual"

    def _park_control_request(
        self,
        kind: str,
        args: dict[str, Any],
        node: NodeSession | None = None,
    ) -> dict[str, Any]:
        node_type = str(args.get("nodeType") or (node["nodeType"] if node else ""))
        request: ControlRequest = {
            "id": str(uuid4()),
            "kind": kind,
            "status": "pending",
            "createdAt": now_iso(),
            "nodeType": node_type,
            "args": args,
            "message": self._control_request_message(kind, node_type, args),
        }
        if node:
            request["nodeSessionId"] = node["id"]
        self.store.set_pending_control(request)
        self.state = self.store.read_state()
        return {
            "status": "pending_human_decision",
            "controlRequestId": request["id"],
            "kind": kind,
            "nodeType": node_type,
            "message": request["message"],
        }

    def _control_request_message(self, kind: str, node_type: str, args: dict[str, Any]) -> str:
        if kind == "enter_node":
            return f"Agent requested entering node {node_type}: {args.get('rationale', '')}"
        if kind == "finish_node":
            return f"Agent requested finishing node {node_type}: {args.get('summary', '')}"
        return kind

    async def _handle_node_runner_return(self, node: NodeSession) -> None:
        self.state = self.store.read_state()
        latest = self.store.read_node_session(node["id"]) or node
        if latest.get("status") == "waiting_approval":
            return
        if latest.get("status") == "completed":
            if self._control_mode() == "auto":
                await self._maybe_auto_enter_next_node(latest)
            return
        if latest.get("status") in {"paused", "failed", "exited"}:
            return
        self.store.append_timeline({
            "type": "node_protocol_error",
            "timestamp": now_iso(),
            "nodeSessionId": latest.get("id"),
            "nodeType": latest.get("nodeType"),
            "message": "Node runner returned without calling finish_node MCP.",
        })
        await self.finish_node({
            "success": False,
            "summary": "Node runner returned without calling finish_node MCP.",
            "goalMet": False,
            "outputPaths": [],
        })

    async def _maybe_auto_enter_next_node(self, finished_node: NodeSession) -> None:
        self._ensure_initialized()
        assert self.state
        if self._control_mode() != "auto":
            return
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
        if latest["nodeType"] == "iterative-solving":
            if latest.get("loopDecision") == "continue":
                return "iterative-solving"
            if latest.get("loopDecision") == "exit":
                return "final-summary"
            if latest.get("nextNode"):
                return latest.get("nextNode")
            if latest.get("goalMet") is True:
                return get_next_node(latest["nodeType"])
            return None
        if latest.get("nextNode"):
            return latest.get("nextNode")
        return get_next_node(latest["nodeType"])

    def _normalize_next_node(self, value: Any) -> NodeType | None:
        if value is None:
            return None
        node = str(value).strip()
        if not node or node == "none":
            return None
        if node not in NODE_SPECS_BY_TYPE:
            raise RuntimeError(f"Invalid nextNode from MCP finish_node: {node}")
        return node

    def _normalize_loop_decision(self, value: Any) -> str | None:
        if value is None:
            return None
        decision = str(value).strip().lower()
        if not decision or decision == "none":
            return None
        if decision not in {"continue", "exit"}:
            raise RuntimeError(f"Invalid loopDecision from MCP finish_node: {decision}")
        return decision

    def _validate_finish_control(
        self,
        node_type: NodeType,
        success: bool,
        next_node: NodeType | None,
        loop_decision: str | None,
    ) -> None:
        if node_type != "iterative-solving":
            return
        if success and not next_node and not loop_decision:
            raise RuntimeError("iterative-solving finish_node requires loopDecision or nextNode.")
        if loop_decision == "continue" and next_node not in {None, "iterative-solving"}:
            raise RuntimeError("iterative-solving loopDecision=continue requires nextNode=iterative-solving.")
        if loop_decision == "exit" and next_node not in {None, "final-summary"}:
            raise RuntimeError("iterative-solving loopDecision=exit requires nextNode=final-summary.")

    def _ensure_initialized(self) -> None:
        if not self.state:
            self.initialize()

    def _knowledge_graph_llm_config(self) -> LlmConfig:
        main = read_effective_llm_config(self.workspace_path)
        if not self.store.knowledge_graph_llm_path.exists():
            return main
        graph = self.store.read_knowledge_graph_llm_config()
        return LlmConfig(
            authMode=graph.get("authMode") if graph.get("authMode") in {"manual", "sdk-default"} else main.authMode,
            model=graph.get("model") or main.model,
            apiKey=graph.get("apiKey") or main.apiKey,
            baseUrl=graph.get("baseUrl") or main.baseUrl,
            protocol=graph.get("protocol") or main.protocol,
            contextWindow=graph.get("contextWindow") or main.contextWindow,
        )

    def _llm_config_from_dict(self, raw: dict[str, Any]) -> LlmConfig:
        protocol = raw.get("protocol") if raw.get("protocol") in {"anthropic", "openai-compat"} else None
        context = raw.get("contextWindow") if raw.get("contextWindow") in {"200k", "1m"} else None
        auth = raw.get("authMode") if raw.get("authMode") in {"manual", "sdk-default"} else "manual"
        return LlmConfig(
            authMode=auth,
            model=raw.get("model") if isinstance(raw.get("model"), str) else "",
            apiKey=raw.get("apiKey") if isinstance(raw.get("apiKey"), str) else None,
            baseUrl=raw.get("baseUrl") if isinstance(raw.get("baseUrl"), str) else None,
            protocol=protocol,
            contextWindow=context,
        )

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
        mcp_server = create_harness_mcp_server(
            session_role="main",
            enter_node=self.request_enter_node,
            query_knowledge=self.request_query_knowledge,
        )
        if mcp_server is None:
            raise RuntimeError("Claude Code SDK MCP server is required for node control but could not be created.")
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
        mcp_server = create_harness_mcp_server(
            session_role="node",
            finish_node=self.request_finish_node,
            query_knowledge=self.request_query_knowledge,
            record_artifact=self.record_artifact,
            record_run=self.record_run,
            get_runtime_settings=self.get_runtime_settings,
        )
        if mcp_server is None:
            raise RuntimeError("Claude Code SDK MCP server is required for node control but could not be created.")

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
