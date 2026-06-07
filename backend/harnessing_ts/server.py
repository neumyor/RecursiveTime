from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import unquote

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from harnessing_ts.orchestrator import HarnessOrchestrator
from harnessing_ts.paths import default_workspace_path, frontend_root
from harnessing_ts.settings.llm import build_sdk_invocation_config, mask_llm_config, mask_sdk_invocation_config, read_effective_llm_config


class SendRequest(BaseModel):
    text: str


class ClearLogsRequest(BaseModel):
    scope: str = "main"


class InterruptRequest(BaseModel):
    reason: str | None = None


class ControlDecisionRequest(BaseModel):
    reason: str | None = None


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
    orchestrator.initialize()
    app = FastAPI(title="HarnessingTS")
    app.state.orchestrator = orchestrator
    app.state.workspace_path = workspace_path
    app.state.dry_run = dry_run
    app.state.debug_enabled = debug_enabled
    app.state.run_task = None

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
            raise HTTPException(status_code=409, detail="a harness run is already active")
        app.state.run_task = asyncio.create_task(_run_main_turn(orchestrator, text))
        setattr(orchestrator, "_server_run_task", app.state.run_task)
        return {"accepted": True, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/interrupt")
    async def interrupt(request: InterruptRequest) -> dict[str, Any]:
        try:
            result = await orchestrator.interrupt_current(request.reason)
        except Exception as exc:
            orchestrator.store.append_timeline({"type": "interrupt_error", "timestamp": now_iso_for_server(), "message": str(exc)})
            result = {"target": "unknown", "error": str(exc), "state": orchestrator.get_state()}
        return {"result": result, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/control/approve")
    async def approve_control() -> dict[str, Any]:
        current = app.state.run_task
        if current is not None and not current.done():
            raise HTTPException(status_code=409, detail="a harness run is already active")
        app.state.run_task = asyncio.create_task(_run_control_approval(orchestrator))
        setattr(orchestrator, "_server_run_task", app.state.run_task)
        return {"accepted": True, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/control/reject")
    async def reject_control(request: ControlDecisionRequest) -> dict[str, Any]:
        result = orchestrator.reject_pending_control(request.reason)
        return {"result": result, "bootstrap": _bootstrap(orchestrator, workspace_path, dry_run, debug_enabled)}

    @app.post("/api/debug/clear-logs")
    async def clear_logs(request: ClearLogsRequest) -> dict[str, Any]:
        if not debug_enabled:
            raise HTTPException(status_code=403, detail="debug actions are disabled")
        orchestrator.clear_debug_logs("all" if request.scope == "all" else "main")
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
    payload = {
        "state": orchestrator.get_state(),
        "timeline": orchestrator.get_timeline(),
        "mainParts": orchestrator.get_main_parts(),
        "nodes": orchestrator.get_node_sessions(),
        "nodePartsById": orchestrator.get_node_parts_by_id(),
        "nodeSpecs": orchestrator.get_node_specs(),
        "fileTree": orchestrator.get_file_tree(),
        "llmConfig": _masked_llm_config(workspace_path),
        "dryRun": dry_run,
        "debugEnabled": debug_enabled,
        "runtime": {
            "running": _task_running(getattr(orchestrator, "_server_run_task", None)),
            "workspaceUv": orchestrator.get_runtime_status(),
        },
    }
    return payload


def _live(orchestrator: HarnessOrchestrator) -> dict[str, Any]:
    return {
        "state": orchestrator.get_state(),
        "timeline": orchestrator.get_timeline(),
        "mainParts": orchestrator.get_main_parts(),
        "nodes": orchestrator.get_node_sessions(),
        "nodePartsById": orchestrator.get_node_parts_by_id(),
        "runtime": {
            "running": _task_running(getattr(orchestrator, "_server_run_task", None)),
            "workspaceUv": orchestrator.get_runtime_status(),
        },
    }


async def _run_main_turn(orchestrator: HarnessOrchestrator, text: str) -> None:
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


async def _run_control_approval(orchestrator: HarnessOrchestrator) -> None:
    setattr(orchestrator, "_server_run_task", asyncio.current_task())
    try:
        await orchestrator.approve_pending_control()
    except Exception as exc:
        orchestrator.store.append_timeline({"type": "error", "timestamp": now_iso_for_server(), "message": str(exc)})
        orchestrator.store.append_main_part(system_error_part_for_server(str(exc)))
    finally:
        setattr(orchestrator, "_server_run_task", None)


def _task_running(task: Any) -> bool:
    return task is not None and not task.done()


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
    cfg = read_effective_llm_config(workspace_path)
    sdk = build_sdk_invocation_config(cfg)
    return {"config": mask_llm_config(cfg), "sdk": mask_sdk_invocation_config(sdk)}


def _format_exception(exc: Exception) -> str:
    if isinstance(exc, BaseExceptionGroup):
        messages = [str(item) for item in exc.exceptions if str(item)]
        return "; ".join(messages) or str(exc)
    return str(exc) or exc.__class__.__name__


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "4327"))
    print(f"HarnessingTS web UI: http://{host}:{port}")
    print(f"Workspace: {default_workspace_path()}")
    print(f"Control mode: {os.getenv('TS_HARNESS_CONTROL_MODE', 'auto')}")
    if os.getenv("TS_HARNESS_DRY_RUN") == "true":
        print("Dry-run mode enabled")
    if os.getenv("TS_HARNESS_DEBUG") == "true":
        print("Debug actions enabled")
    uvicorn.run("harnessing_ts.server:create_app", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()
