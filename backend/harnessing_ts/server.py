from __future__ import annotations

import asyncio
import mimetypes
import os
import socket
import sys
from typing import Any
from urllib.parse import unquote

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from harnessing_ts.api.payloads import build_bootstrap_payload, build_live_payload, masked_llm_config
from harnessing_ts.api.realtime import RealtimeEvent, RealtimeEventBroker
from harnessing_ts.orchestrator import HarnessOrchestrator
from harnessing_ts.paths import default_workspace_path, frontend_root
from harnessing_ts.variants import resolve_variant, variant_help_text


class SendRequest(BaseModel):
    text: str


class ClearLogsRequest(BaseModel):
    scope: str = "main"
    confirmReset: bool = False


class InterruptRequest(BaseModel):
    reason: str | None = None


class ControlDecisionRequest(BaseModel):
    reason: str | None = None


class RuntimeSettingsRequest(BaseModel):
    iterativeCandidateCount: int | None = None
    knowledgeGraphExtractionDepth: int | None = None


class KnowledgeGraphBuildRequest(BaseModel):
    trigger: str | None = "manual"


class KnowledgeGraphLlmConfigRequest(BaseModel):
    authMode: str | None = None
    protocol: str | None = None
    model: str | None = None
    apiKey: str | None = None
    baseUrl: str | None = None
    contextWindow: str | None = None


class ReferenceFeatureBuildRequest(BaseModel):
    trigger: str | None = "manual"


class ReferenceFeatureRunRequest(BaseModel):
    input: Any


class MainLlmConfigRequest(BaseModel):
    authMode: str | None = None
    protocol: str | None = None
    model: str | None = None
    apiKey: str | None = None
    baseUrl: str | None = None
    contextWindow: str | None = None


class KnowledgeQueryRequest(BaseModel):
    domain: str | None = None
    question: str
    context: dict[str, Any] | None = None
    observations: list[str] | None = None
    includeEvidence: bool = False


def create_app() -> FastAPI:
    workspace_path = default_workspace_path()
    dry_run = os.getenv("TS_HARNESS_DRY_RUN") == "true"
    debug_enabled = os.getenv("TS_HARNESS_DEBUG") == "true"
    control_mode = os.getenv("TS_HARNESS_CONTROL_MODE", "auto").strip().lower()
    if control_mode not in {"auto", "manual"}:
        control_mode = "auto"
    frontend = frontend_root()
    web_root = frontend / "dist" if (frontend / "dist").exists() else frontend
    orchestrator = HarnessOrchestrator(workspace_path, dry_run=dry_run, locale="zh", mode=control_mode)
    orchestrator.initialize(reporter=_startup_report)
    _print_ready_urls()
    app = FastAPI(title="HarnessingTS")
    realtime = RealtimeEventBroker()
    orchestrator.set_realtime_event_sink(realtime.publish)
    app.state.orchestrator = orchestrator
    app.state.realtime = realtime
    app.state.workspace_path = workspace_path
    app.state.dry_run = dry_run
    app.state.debug_enabled = debug_enabled
    app.state.run_task = None
    app.state.knowledge_graph_task = None
    app.state.chain_summary_task = None

    @app.middleware("http")
    async def no_store_cache(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception(_request: Any, exc: Exception) -> JSONResponse:
        return JSONResponse({"error": _format_exception(exc)}, status_code=500)

    @app.get("/api/bootstrap")
    async def bootstrap() -> dict[str, Any]:
        return _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)

    @app.get("/api/live")
    async def live() -> dict[str, Any]:
        return _live(orchestrator)

    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        async def stream():
            queue = realtime.subscribe()
            try:
                initial = RealtimeEvent(0, "bootstrap_snapshot", {
                    "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled),
                })
                yield initial.as_sse()
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield event.as_sse()
            finally:
                realtime.unsubscribe(queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return orchestrator.get_state()

    @app.get("/api/timeline")
    async def timeline() -> list[dict[str, Any]]:
        return orchestrator.get_timeline()

    @app.get("/api/main-log")
    async def main_log() -> list[dict[str, Any]]:
        return orchestrator.get_main_parts()

    @app.get("/api/nodes")
    async def nodes() -> list[dict[str, Any]]:
        return orchestrator.get_node_sessions()

    @app.get("/api/nodes/{node_session_id}/log")
    async def node_log(node_session_id: str) -> list[dict[str, Any]]:
        return orchestrator.get_node_parts(node_session_id)

    @app.get("/api/node-specs")
    async def node_specs() -> list[dict[str, Any]]:
        return orchestrator.get_node_specs()

    @app.get("/api/llm-config")
    async def llm_config() -> dict[str, Any]:
        return _masked_llm_config(workspace_path)

    @app.get("/api/runtime-settings")
    async def runtime_settings() -> dict[str, Any]:
        return orchestrator.get_runtime_settings()

    @app.post("/api/runtime-settings")
    async def update_runtime_settings(request: RuntimeSettingsRequest) -> dict[str, Any]:
        settings = orchestrator.update_runtime_settings(request.model_dump(exclude_none=True))
        return {"settings": settings, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.get("/api/knowledge-graph")
    async def knowledge_graph() -> dict[str, Any]:
        return orchestrator.get_knowledge_graph()

    @app.get("/api/knowledge-base/summary")
    async def knowledge_base_summary() -> dict[str, Any]:
        return orchestrator.get_knowledge_base_summary()

    @app.get("/api/knowledge-base/cards")
    async def knowledge_base_cards(kind: str, limit: int = 200) -> dict[str, Any]:
        try:
            return orchestrator.get_knowledge_base_cards(kind, limit)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/api/knowledge/query")
    async def query_knowledge(request: KnowledgeQueryRequest) -> dict[str, Any]:
        if not request.question.strip():
            raise HTTPException(status_code=400, detail="question required")
        return await orchestrator.query_knowledge(
            request.question,
            request.domain,
            request.context,
            request.observations,
            include_evidence=request.includeEvidence,
        )

    @app.post("/v1/knowledge/query")
    async def v1_query_knowledge(request: KnowledgeQueryRequest) -> dict[str, Any]:
        if not request.question.strip():
            raise HTTPException(status_code=400, detail="question required")
        return await orchestrator.query_knowledge(
            request.question,
            request.domain,
            request.context,
            request.observations,
            include_evidence=request.includeEvidence,
        )

    @app.get("/api/knowledge/search/notes")
    async def search_knowledge_notes(q: str, top_k: int = 5) -> list[dict[str, Any]]:
        return orchestrator.search_knowledge_notes(q, top_k)

    @app.get("/api/knowledge/search/evidence")
    async def search_evidence(q: str, top_k: int = 5) -> list[dict[str, Any]]:
        return orchestrator.search_evidence_notes(q, top_k)

    @app.get("/api/knowledge/search/graph")
    async def search_graph(q: str, relation_type: str | None = None, top_k: int = 10) -> list[dict[str, Any]]:
        return orchestrator.search_knowledge_graph(q, relation_type, top_k)

    @app.get("/api/knowledge/graph/neighbors")
    async def graph_neighbors(concept: str, depth: int = 1) -> dict[str, Any]:
        return orchestrator.get_knowledge_neighbors(concept, depth)

    @app.get("/api/knowledge/supporting-evidence")
    async def supporting_evidence(id: str, top_k: int = 8) -> list[dict[str, Any]]:
        return orchestrator.get_knowledge_supporting_evidence(id, top_k)

    @app.get("/api/knowledge/next-checks")
    async def next_checks(q: str, top_k: int = 5) -> list[dict[str, Any]]:
        return orchestrator.suggest_knowledge_next_checks(q, top_k)

    @app.post("/api/knowledge-graph/build")
    async def trigger_knowledge_graph_build(request: KnowledgeGraphBuildRequest) -> dict[str, Any]:
        accepted = _start_knowledge_graph_build(app, orchestrator, realtime, request.trigger or "manual", [])
        return {"accepted": accepted, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/knowledge-graph/pause")
    async def pause_knowledge_graph_build(request: InterruptRequest) -> dict[str, Any]:
        await orchestrator.pause_knowledge_graph_build(request.reason)
        realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})
        return {"bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/knowledge-graph/continue")
    async def continue_knowledge_graph_build() -> dict[str, Any]:
        accepted = _start_knowledge_graph_build(app, orchestrator, realtime, "continue", [])
        return {"accepted": accepted, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.get("/api/knowledge-graph/status")
    async def knowledge_graph_status() -> dict[str, Any]:
        return orchestrator.get_knowledge_graph_build_status()

    @app.get("/api/knowledge-graph/log")
    async def knowledge_graph_log() -> list[dict[str, Any]]:
        return orchestrator.get_knowledge_graph_parts()

    @app.get("/api/knowledge-graph/llm-config")
    async def knowledge_graph_llm_config() -> dict[str, Any]:
        return orchestrator.get_knowledge_graph_llm_config()

    @app.post("/api/knowledge-graph/llm-config")
    async def update_knowledge_graph_llm_config(request: KnowledgeGraphLlmConfigRequest) -> dict[str, Any]:
        config = orchestrator.update_knowledge_graph_llm_config(request.model_dump(exclude_none=True))
        return {"config": config, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.get("/api/chain-summary")
    async def chain_summary() -> dict[str, Any]:
        return orchestrator.get_chain_summary()

    @app.get("/api/chain-summary/status")
    async def chain_summary_status() -> dict[str, Any]:
        return orchestrator.get_chain_summary_status()

    @app.get("/api/chain-summary/log")
    async def chain_summary_log() -> list[dict[str, Any]]:
        return orchestrator.get_chain_summary_parts()

    @app.post("/api/chain-summary/build")
    async def trigger_chain_summary_build() -> dict[str, Any]:
        accepted = _start_chain_summary_build(app, orchestrator, realtime, "manual")
        return {"accepted": accepted, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/chain-summary/pause")
    async def pause_chain_summary_build(request: InterruptRequest) -> dict[str, Any]:
        await orchestrator.pause_chain_summary_build(request.reason)
        realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})
        return {"bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/llm-config")
    async def update_main_llm_config(request: MainLlmConfigRequest) -> dict[str, Any]:
        config = orchestrator.update_main_llm_config(request.model_dump(exclude_none=True))
        return {"config": config, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.get("/api/reference-features/status")
    async def reference_feature_status() -> dict[str, Any]:
        return orchestrator.get_reference_feature_status()

    @app.get("/api/reference-features/tool")
    async def reference_feature_tool() -> dict[str, Any]:
        return orchestrator.get_reference_feature_tool()

    @app.post("/api/reference-features/run")
    async def run_reference_feature_tool(request: ReferenceFeatureRunRequest) -> dict[str, Any]:
        return orchestrator.request_extract_reference_features({"input": request.input})

    @app.get("/api/files/tree")
    async def file_tree() -> dict[str, Any]:
        return orchestrator.get_file_tree()

    @app.get("/api/files/content")
    async def file_content(path: str) -> dict[str, Any]:
        try:
            return orchestrator.read_workspace_file(unquote(path))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="file not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None

    @app.get("/api/files/preview")
    async def file_preview(path: str) -> FileResponse:
        rel_path = unquote(path).strip().lstrip("/")
        target = (workspace_path / rel_path).resolve()
        workspace_root = workspace_path.resolve()
        if target != workspace_root and workspace_root not in target.parents:
            raise HTTPException(status_code=403, detail="preview is limited to workspace files")
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if not (media_type.startswith("image/") or media_type == "application/pdf"):
            raise HTTPException(status_code=415, detail="preview only supports images and PDFs")
        response = FileResponse(target, media_type=media_type, filename=target.name)
        response.headers["Content-Disposition"] = f'inline; filename="{target.name}"'
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/references/preview")
    async def reference_preview(path: str) -> FileResponse:
        rel_path = unquote(path).strip().lstrip("/")
        target = (workspace_path / rel_path).resolve()
        references_root = (workspace_path / "references").resolve()
        if target != references_root and references_root not in target.parents:
            raise HTTPException(status_code=403, detail="reference preview is limited to references/")
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="reference file not found")
        media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        response = FileResponse(target, media_type=media_type, filename=target.name)
        response.headers["Content-Disposition"] = f'inline; filename="{target.name}"'
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/api/references/upload")
    async def upload_references(files: list[UploadFile] = File(...)) -> dict[str, Any]:
        uploaded: list[dict[str, Any]] = []
        for file in files:
            content = await file.read()
            path = orchestrator.upload_reference_file(file.filename or "reference", content)
            uploaded.append({"path": path, "size": len(content)})
        return {"uploaded": uploaded, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/data/raw/upload-zip")
    async def upload_raw_data_zip(file: UploadFile = File(...)) -> dict[str, Any]:
        content = await file.read()
        try:
            result = orchestrator.upload_raw_data_zip(file.filename or "raw-data.zip", content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"uploaded": result, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/send")
    async def send(request: SendRequest) -> dict[str, Any]:
        text = request.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text required")
        current = app.state.run_task
        if current is not None and not current.done():
            if not _active_node_is_paused(orchestrator):
                raise HTTPException(status_code=409, detail="a harness run is already active")
            try:
                await asyncio.wait_for(asyncio.shield(current), timeout=2.0)
            except TimeoutError:
                raise HTTPException(status_code=409, detail="paused node is still settling; retry shortly") from None
        app.state.run_task = asyncio.create_task(_run_main_turn(orchestrator, text, realtime))
        setattr(orchestrator, "_server_run_task", app.state.run_task)
        realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})
        return {"accepted": True, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/interrupt")
    async def interrupt(request: InterruptRequest) -> dict[str, Any]:
        try:
            result = await orchestrator.interrupt_current(request.reason)
        except Exception as exc:
            orchestrator.store.append_timeline({"type": "interrupt_error", "timestamp": now_iso_for_server(), "message": str(exc)})
            result = {"target": "unknown", "error": str(exc), "state": orchestrator.get_state()}
        realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})
        return {"result": result, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/control/approve")
    async def approve_control() -> dict[str, Any]:
        current = app.state.run_task
        if current is not None and not current.done():
            raise HTTPException(status_code=409, detail="a harness run is already active")
        app.state.run_task = asyncio.create_task(_run_control_approval(orchestrator, realtime))
        setattr(orchestrator, "_server_run_task", app.state.run_task)
        realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})
        return {"accepted": True, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/control/reject")
    async def reject_control(request: ControlDecisionRequest) -> dict[str, Any]:
        result = orchestrator.reject_pending_control(request.reason)
        return {"result": result, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/debug/clear-logs")
    async def clear_logs(request: ClearLogsRequest) -> dict[str, Any]:
        if not debug_enabled:
            raise HTTPException(status_code=403, detail="debug actions are disabled")
        if request.scope not in {"main", "chat", "all"}:
            raise HTTPException(status_code=400, detail="invalid clear scope")
        if request.scope in {"chat", "all"}:
            if not request.confirmReset:
                raise HTTPException(status_code=400, detail="reset confirmation required")
            if _task_running(app.state.run_task) or _task_running(app.state.knowledge_graph_task) or _task_running(app.state.chain_summary_task):
                raise HTTPException(status_code=409, detail="cannot reset workspace while a run is active")
        await orchestrator.clear_debug_logs(request.scope)
        return {"ok": True, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    if web_root.exists():
        assets_root = web_root / "assets"
        app.mount("/assets", StaticFiles(directory=str(assets_root if assets_root.exists() else web_root)), name="assets")

        @app.get("/{full_path:path}")
        async def static_files(full_path: str) -> FileResponse:
            target = (web_root / (full_path or "index.html")).resolve()
            if not str(target).startswith(str(web_root.resolve())):
                raise HTTPException(status_code=403, detail="Forbidden")
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                target = web_root / "index.html"
            return FileResponse(target)

    return app


def _bootstrap(orchestrator: HarnessOrchestrator, workspace_path: Path, dry_run: bool, debug_enabled: bool) -> dict[str, Any]:
    return build_bootstrap_payload(
        orchestrator=orchestrator,
        workspace_path=workspace_path,
        dry_run=dry_run,
        debug_enabled=debug_enabled,
        task_running=_task_running,
    )


def _live(orchestrator: HarnessOrchestrator) -> dict[str, Any]:
    return build_live_payload(orchestrator=orchestrator, task_running=_task_running)


async def _run_main_turn(orchestrator: HarnessOrchestrator, text: str, realtime: RealtimeEventBroker) -> None:
    setattr(orchestrator, "_server_run_task", asyncio.current_task())
    try:
        await orchestrator.send_main_user_message(text)
    except RuntimeError as exc:
        if "Interrupted by user" not in str(exc):
            orchestrator.store.append_timeline({"type": "error", "timestamp": now_iso_for_server(), "message": str(exc)})
            orchestrator.store.append_main_part(system_error_part_for_server(str(exc)))
    except Exception as exc:
        orchestrator.store.append_timeline({"type": "error", "timestamp": now_iso_for_server(), "message": str(exc)})
        orchestrator.store.append_main_part(system_error_part_for_server(str(exc)))
    finally:
        setattr(orchestrator, "_server_run_task", None)
        realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})


async def _run_control_approval(orchestrator: HarnessOrchestrator, realtime: RealtimeEventBroker) -> None:
    setattr(orchestrator, "_server_run_task", asyncio.current_task())
    try:
        await orchestrator.approve_pending_control()
    except Exception as exc:
        orchestrator.store.append_timeline({"type": "error", "timestamp": now_iso_for_server(), "message": str(exc)})
        orchestrator.store.append_main_part(system_error_part_for_server(str(exc)))
    finally:
        setattr(orchestrator, "_server_run_task", None)
        realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})


def _start_knowledge_graph_build(
    app: FastAPI,
    orchestrator: HarnessOrchestrator,
    realtime: RealtimeEventBroker,
    trigger: str,
    uploaded_paths: list[str],
) -> bool:
    current = getattr(app.state, "knowledge_graph_task", None)
    if current is not None and not current.done():
        orchestrator.store.append_timeline({
            "type": "knowledge_graph_build_skipped",
            "timestamp": now_iso_for_server(),
            "message": "Knowledge graph build is already running.",
            "payload": {"trigger": trigger, "uploadedPaths": uploaded_paths},
        })
        return False
    app.state.knowledge_graph_task = asyncio.create_task(
        _run_knowledge_graph_build(orchestrator, realtime, trigger, uploaded_paths)
    )
    setattr(orchestrator, "_server_knowledge_graph_task", app.state.knowledge_graph_task)
    realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})
    return True


async def _run_knowledge_graph_build(
    orchestrator: HarnessOrchestrator,
    realtime: RealtimeEventBroker,
    trigger: str,
    uploaded_paths: list[str],
) -> None:
    setattr(orchestrator, "_server_knowledge_graph_task", asyncio.current_task())
    try:
        await orchestrator.build_knowledge_graph(trigger, uploaded_paths)
    except Exception:
        # The orchestrator records failure status and timeline details.
        pass
    finally:
        setattr(orchestrator, "_server_knowledge_graph_task", None)
        realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})


def _start_chain_summary_build(
    app: FastAPI,
    orchestrator: HarnessOrchestrator,
    realtime: RealtimeEventBroker,
    trigger: str,
) -> bool:
    current = getattr(app.state, "chain_summary_task", None)
    if current is not None and not current.done():
        orchestrator.store.append_timeline({
            "type": "chain_summary_build_skipped",
            "timestamp": now_iso_for_server(),
            "message": "Chain builder is already running.",
            "payload": {"trigger": trigger},
        })
        return False
    app.state.chain_summary_task = asyncio.create_task(_run_chain_summary_build(orchestrator, realtime, trigger))
    setattr(orchestrator, "_server_chain_summary_task", app.state.chain_summary_task)
    realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})
    return True


async def _run_chain_summary_build(
    orchestrator: HarnessOrchestrator,
    realtime: RealtimeEventBroker,
    trigger: str,
) -> None:
    setattr(orchestrator, "_server_chain_summary_task", asyncio.current_task())
    try:
        await orchestrator.build_chain_summary(trigger)
    except Exception:
        # The orchestrator records failure status and timeline details.
        pass
    finally:
        setattr(orchestrator, "_server_chain_summary_task", None)
        realtime.publish("live_snapshot", {"snapshot": _live(orchestrator)})


def _task_running(task: Any) -> bool:
    return task is not None and not task.done()


def _active_node_is_paused(orchestrator: HarnessOrchestrator) -> bool:
    state = orchestrator.get_state()
    node_id = state.get("activeNodeSessionId")
    if not node_id:
        return False
    node = orchestrator.store.read_node_session(node_id)
    return bool(node and node.get("status") == "paused")


def now_iso_for_server() -> str:
    from harnessing_ts.state.workspace_store import now_iso

    return now_iso()


def system_error_part_for_server(message: str) -> dict[str, Any]:
    from harnessing_ts.agent.translate import system_text_part

    part = system_text_part(f"Harness error: {message}")
    part["type"] = "result"
    part["raw"] = {"is_error": True, "result": message}
    return part


def _masked_llm_config(workspace_path: Path) -> dict[str, Any]:
    return masked_llm_config(workspace_path)


def _format_exception(exc: Exception) -> str:
    if isinstance(exc, BaseExceptionGroup):
        messages = [str(item) for item in exc.exceptions if str(item)]
        return "; ".join(messages) or str(exc)
    return str(exc) or exc.__class__.__name__


def main() -> None:
    try:
        host = _startup_host()
        port = _startup_port()
        control_mode = _startup_control_mode()
        variant = resolve_variant()
    except RuntimeError as exc:
        _print_startup_error(str(exc), include_variant_help=True)
        raise SystemExit(2) from None
    except ValueError as exc:
        _print_startup_error(str(exc))
        raise SystemExit(2) from None
    print(f"Workspace: {default_workspace_path()}")
    print(f"Control mode: {control_mode}")
    print(f"Ablation variant: {variant.id} · {variant.name}")
    if os.getenv("TS_HARNESS_DRY_RUN") == "true":
        print("Dry-run mode enabled")
    if os.getenv("TS_HARNESS_DEBUG") == "true":
        print("Debug actions enabled")
    print("Initializing backend and runtime workspace. The web UI URL will be printed when ready.")
    uvicorn.run("harnessing_ts.server:create_app", host=host, port=port, factory=True)


def _startup_host() -> str:
    host = os.getenv("HOST", "127.0.0.1").strip()
    if not host:
        raise ValueError("Invalid HOST: empty value. Use HOST=127.0.0.1 for local access or HOST=0.0.0.0 for LAN/server access.")
    return host


def _startup_port() -> int:
    raw = os.getenv("PORT", "4327").strip()
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid PORT={raw!r}; expected an integer from 1 to 65535, for example PORT=4327.") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"Invalid PORT={raw!r}; expected a TCP port from 1 to 65535, for example PORT=4327.")
    return port


def _startup_control_mode() -> str:
    raw = os.getenv("TS_HARNESS_CONTROL_MODE", "auto").strip().lower()
    if raw not in {"auto", "manual"}:
        raise ValueError(
            f"Invalid TS_HARNESS_CONTROL_MODE={raw!r}; expected 'auto' or 'manual'. "
            "Use auto for automatic node transitions or manual for UI approval."
        )
    return raw


def _print_startup_error(message: str, *, include_variant_help: bool = False) -> None:
    print("HarnessingTS startup configuration error", file=sys.stderr)
    print(message, file=sys.stderr)
    if include_variant_help:
        print("", file=sys.stderr)
        print("Valid variant configuration:", file=sys.stderr)
        print(variant_help_text(), file=sys.stderr)


def _startup_report(message: str) -> None:
    print(message, flush=True)


def _print_ready_urls() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "4327"))
    print(f"HarnessingTS web UI ready: http://{host}:{port}", flush=True)
    if host in {"0.0.0.0", "::"}:
        lan_host = _best_effort_lan_host()
        if lan_host:
            print(f"LAN access URL: http://{lan_host}:{port}", flush=True)


def _best_effort_lan_host() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            host = sock.getsockname()[0]
            return host if host and not host.startswith("127.") else None
    except OSError:
        try:
            host = socket.gethostbyname(socket.gethostname())
            return host if host and not host.startswith("127.") else None
        except OSError:
            return None


if __name__ == "__main__":
    main()
