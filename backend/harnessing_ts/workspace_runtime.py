from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harnessing_ts.state.jsonl import write_json


DEFAULT_PYTHON_VERSION = "3.11"
DEFAULT_DEPENDENCIES = [
    "python-docx>=1.1.2",
    "numpy>=1.26",
    "pandas>=2.2",
    "scipy>=1.12",
    "scikit-learn>=1.4",
    "matplotlib>=3.8",
    "sktime>=0.35",
]


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

    created_pyproject = _ensure_pyproject(root)
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
        env=_uv_sync_env(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=int(os.getenv("TS_HARNESS_WORKSPACE_UV_TIMEOUT", "600")),
        check=False,
    )
    if result.returncode == 0:
        status = _status(root, "ready", "workspace uv environment synchronized")
    else:
        status = _status(root, "failed", "uv sync failed")
    status.update({
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    })
    write_json(status_path, status)
    return status


def _ensure_pyproject(root: Path) -> bool:
    path = root / "pyproject.toml"
    if path.exists():
        return False
    deps = "\n".join(f'  "{dep}",' for dep in DEFAULT_DEPENDENCIES)
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
''', encoding="utf-8")
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


def _uv_sync_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env["UV_PROJECT"] = str(root)
    return env


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
