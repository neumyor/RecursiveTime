from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harnessing_ts.state.jsonl import write_json
from harnessing_ts.runtime_base import DEFAULT_WORKSPACE_DEPENDENCIES, apply_runtime_base_env, read_runtime_base, workspace_base_dependencies, workspace_torch_source


DEFAULT_PYTHON_VERSION = "3.11"
DEFAULT_DEPENDENCIES = DEFAULT_WORKSPACE_DEPENDENCIES


def ensure_workspace_uv_environment(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    status_path = root / "state" / "runtime.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)

    if os.getenv("TS_HARNESS_SKIP_WORKSPACE_UV") == "true":
        status = _status(root, "skipped", "TS_HARNESS_SKIP_WORKSPACE_UV=true")
        write_json(status_path, status)
        return status

    uv = shutil.which("uv")
    if not uv:
        status = _status(root, "failed", "uv executable not found in PATH")
        write_json(status_path, status)
        return status

    runtime_base = read_runtime_base()
    created_pyproject = _ensure_pyproject(root, runtime_base)
    _ensure_python_version(root)

    should_sync = created_pyproject or _should_sync(root)
    if not should_sync:
        status = _status(root, "ready", "workspace uv environment already synchronized")
        write_json(status_path, status)
        return status

    command = [uv, "sync", "--python", DEFAULT_PYTHON_VERSION]
    result = subprocess.run(
        command,
        cwd=root,
        env=_uv_sync_env(root, runtime_base),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=int(os.getenv("TS_HARNESS_WORKSPACE_UV_TIMEOUT", "600")),
        check=False,
    )
    if result.returncode == 0:
        message = "workspace uv environment synchronized"
        if runtime_base:
            message += " from project runtime base"
        status = _status(root, "ready", message)
    else:
        status = _status(root, "failed", "uv sync failed")
    status.update({
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    })
    if runtime_base:
        status["runtimeBase"] = runtime_base.get("root")
        status["inheritedPackages"] = runtime_base.get("packages", {})
    write_json(status_path, status)
    return status


def _ensure_pyproject(root: Path, runtime_base: dict[str, Any] | None = None) -> bool:
    path = root / "pyproject.toml"
    if path.exists():
        return False
    base_dependencies = workspace_base_dependencies(runtime_base)
    base_names = {dependency.split("==", 1)[0] for dependency in base_dependencies}
    dependencies = [dep for dep in DEFAULT_DEPENDENCIES if dep.split(">=", 1)[0] not in base_names]
    deps = "\n".join(f'  "{dep}",' for dep in [*base_dependencies, *dependencies])
    path.write_text(f'''[project]
name = "harnessing-ts-workspace"
version = "0.1.0"
description = "Runtime workspace for HarnessingTS agent-generated tools and analyses."
requires-python = ">={DEFAULT_PYTHON_VERSION}"
dependencies = [
{deps}
]

[tool.uv]
package = false
{workspace_torch_source(runtime_base)}''', encoding="utf-8")
    return True


def _ensure_python_version(root: Path) -> None:
    path = root / ".python-version"
    if not path.exists():
        path.write_text(DEFAULT_PYTHON_VERSION + "\n", encoding="utf-8")


def _should_sync(root: Path) -> bool:
    python = root / ".venv" / "bin" / "python"
    lock = root / "uv.lock"
    pyproject = root / "pyproject.toml"
    if not python.exists() or not lock.exists():
        return True
    return pyproject.stat().st_mtime > lock.stat().st_mtime


def _uv_sync_env(root: Path, runtime_base: dict[str, Any] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env["UV_PROJECT"] = str(root)
    return apply_runtime_base_env(env, runtime_base)


def _status(root: Path, state: str, message: str) -> dict[str, Any]:
    return {
        "state": state,
        "message": message,
        "workspace": str(root),
        "venv": str(root / ".venv"),
        "pyproject": str(root / "pyproject.toml"),
        "pythonVersion": DEFAULT_PYTHON_VERSION,
        "updatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
