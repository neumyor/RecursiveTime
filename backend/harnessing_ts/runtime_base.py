from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from harnessing_ts.paths import project_root
from harnessing_ts.state.jsonl import write_json


DEFAULT_PYTHON_VERSION = "3.11"
RUNTIME_BASE_PACKAGES = ("torch", "numpy", "scikit-learn")
STATUS_FILE = "runtime-base.json"


def runtime_base_path() -> Path:
    configured = os.getenv("TS_HARNESS_RUNTIME_BASE")
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / ".runtime-base"


def prepare_runtime_base(
    root: Path | None = None,
    *,
    python_version: str = DEFAULT_PYTHON_VERSION,
    reporter: Callable[[str], None] | None = print,
) -> dict[str, Any]:
    """Build the machine-local dependency base used to seed runtime workspaces."""
    root = (root or runtime_base_path()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    status_path = root / STATUS_FILE
    uv = shutil.which("uv")
    machine = detect_machine()

    if not uv:
        status = _base_status(root, "failed", "uv executable not found in PATH", machine, python_version)
        write_json(status_path, status)
        return status

    _report(reporter, f"[1/4] Detected {machine['system']} {machine['machine']} ({machine['accelerator']}).")
    _report(reporter, f"      {machine['acceleratorDetail']}")
    _report(reporter, f"[2/4] Preparing Python {python_version} runtime base at {root}.")
    _write_base_project(root, python_version)

    env = _base_uv_env(root)
    venv_command = [uv, "venv", "--clear", "--python", python_version, str(root / ".venv")]
    install_command = [
        uv,
        "pip",
        "install",
        "--upgrade",
        "--python",
        str(root / ".venv" / _python_relative_path()),
        "--link-mode",
        _preferred_link_mode(),
        "--torch-backend",
        env["UV_TORCH_BACKEND"],
        *RUNTIME_BASE_PACKAGES,
    ]
    _report(reporter, "[3/4] Resolving and installing torch, numpy, and scikit-learn with uv.")
    _report(reporter, "      PyTorch backend selection: auto (GPU preferred when supported).")
    try:
        result = _run_base_command(venv_command, root, env, 300)
        if result.returncode == 0:
            result = _run_base_command(
                install_command,
                root,
                env,
                int(os.getenv("TS_HARNESS_RUNTIME_BASE_TIMEOUT", "1800")),
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = "runtime base uv installation timed out" if isinstance(exc, subprocess.TimeoutExpired) else f"could not run uv: {exc}"
        status = _base_status(root, "failed", message, machine, python_version)
        status["commands"] = [" ".join(venv_command), " ".join(install_command)]
        write_json(status_path, status)
        return status

    if result.returncode != 0:
        status = _base_status(root, "failed", "runtime base uv installation failed", machine, python_version)
        status.update({"commands": [" ".join(venv_command), " ".join(install_command)], "returncode": result.returncode})
        write_json(status_path, status)
        return status

    _report(reporter, "[4/4] Verifying imports and detected compute backend.")
    verification = _verify_base(root)
    if verification.get("error"):
        status = _base_status(root, "failed", "runtime base verification failed", machine, python_version)
        status.update({"commands": [" ".join(venv_command), " ".join(install_command)], "verification": verification})
        write_json(status_path, status)
        return status

    status = _base_status(root, "ready", "project runtime base is ready", machine, python_version)
    status.update({
        "commands": [" ".join(venv_command), " ".join(install_command)],
        "cache": str(root / "uv-cache"),
        "packages": verification["packages"],
        "torch": verification["torch"],
        "torchBackend": _resolved_torch_backend(verification["torch"], machine, env["UV_TORCH_BACKEND"]),
    })
    write_json(status_path, status)
    _report(reporter, _ready_summary(status))
    return status


def read_runtime_base(
    root: Path | None = None,
    *,
    python_version: str = DEFAULT_PYTHON_VERSION,
) -> dict[str, Any] | None:
    path = (root or runtime_base_path()) / STATUS_FILE
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("state") != "ready":
        return None
    if value.get("pythonVersion") != python_version:
        return None
    recorded_machine = value.get("machine", {})
    current_machine = detect_machine()
    if (
        recorded_machine.get("system") != current_machine["system"]
        or recorded_machine.get("machine") != current_machine["machine"]
        or recorded_machine.get("accelerator") != current_machine["accelerator"]
    ):
        return None
    if not (Path(value.get("venv", "")) / _python_relative_path()).exists():
        return None
    packages = value.get("packages")
    if not isinstance(packages, dict) or not all(packages.get(name) for name in RUNTIME_BASE_PACKAGES):
        return None
    return value


def detect_machine() -> dict[str, str]:
    accelerator = "cpu"
    detail = "No supported GPU runtime detected"
    if platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}:
        accelerator = "apple-mps"
        detail = "Apple Silicon; standard PyTorch wheel with MPS support"
    elif shutil.which("nvidia-smi"):
        accelerator = "nvidia-cuda"
        detail = _command_first_line(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"]) or "NVIDIA GPU detected"
    elif shutil.which("rocminfo") or Path("/opt/rocm").exists():
        accelerator = "amd-rocm"
        detail = "ROCm installation detected"
    return {
        "system": platform.system() or "unknown",
        "release": platform.release(),
        "machine": platform.machine() or "unknown",
        "accelerator": accelerator,
        "acceleratorDetail": detail,
    }


def workspace_base_dependencies(base: dict[str, Any] | None) -> list[str]:
    if not base:
        return []
    packages = base.get("packages", {})
    return [f"{name}=={packages[name]}" for name in RUNTIME_BASE_PACKAGES if packages.get(name)]


def workspace_torch_source(base: dict[str, Any] | None) -> str:
    if not base:
        return ""
    backend = str(base.get("torchBackend", ""))
    if backend in {"", "pypi", "mps"}:
        return ""
    index_name = "pytorch-" + backend.replace(".", "-")
    return f'''\n[tool.uv.sources]
torch = {{ index = "{index_name}" }}

[[tool.uv.index]]
name = "{index_name}"
url = "https://download.pytorch.org/whl/{backend}"
explicit = true
'''


def apply_runtime_base_env(env: dict[str, str], base: dict[str, Any] | None) -> dict[str, str]:
    if not base:
        return env
    cache = base.get("cache")
    if cache:
        env["UV_CACHE_DIR"] = str(cache)
    return env


def _write_base_project(root: Path, python_version: str) -> None:
    dependencies = "\n".join(f'  "{name}",' for name in RUNTIME_BASE_PACKAGES)
    (root / "pyproject.toml").write_text(f'''[project]
name = "harnessing-ts-runtime-base"
version = "0.1.0"
requires-python = ">={python_version}"
dependencies = [
{dependencies}
]

[tool.uv]
package = false
''', encoding="utf-8")
    (root / ".python-version").write_text(python_version + "\n", encoding="utf-8")


def _base_uv_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env["UV_PROJECT"] = str(root)
    env["UV_CACHE_DIR"] = str(root / "uv-cache")
    env["UV_TORCH_BACKEND"] = os.getenv("TS_HARNESS_TORCH_BACKEND", "auto")
    return env


def _run_base_command(command: list[str], root: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, env=env, text=True, timeout=timeout, check=False)


def _preferred_link_mode() -> str:
    return os.getenv("TS_HARNESS_UV_LINK_MODE", "clone" if platform.system() == "Darwin" else "hardlink")


def _verify_base(root: Path) -> dict[str, Any]:
    python = root / ".venv" / _python_relative_path()
    script = '''
import importlib.metadata as metadata
import json
try:
    import torch
    payload = {
        "packages": {name: metadata.version(name) for name in ("torch", "numpy", "scikit-learn")},
        "torch": {
            "cudaAvailable": bool(torch.cuda.is_available()),
            "cudaVersion": torch.version.cuda,
            "hipVersion": torch.version.hip,
            "mpsAvailable": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()),
            "deviceCount": int(torch.cuda.device_count()),
        },
    }
except Exception as exc:
    payload = {"error": f"{type(exc).__name__}: {exc}"}
print(json.dumps(payload))
'''
    try:
        result = subprocess.run([str(python), "-c", script], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}
    if result.returncode != 0:
        return {"error": result.stderr[-2000:] or "verification process failed"}
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"error": result.stdout[-2000:] or "verification produced no JSON"}


def _base_status(root: Path, state: str, message: str, machine: dict[str, str], python_version: str) -> dict[str, Any]:
    return {
        "state": state,
        "message": message,
        "root": str(root),
        "venv": str(root / ".venv"),
        "pythonVersion": python_version,
        "machine": machine,
        "updatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _python_relative_path() -> Path:
    return Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")


def _command_first_line(command: list[str]) -> str:
    try:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""


def _resolved_torch_backend(torch: dict[str, Any], machine: dict[str, str], requested: str) -> str:
    if requested != "auto":
        return requested
    cuda = str(torch.get("cudaVersion") or "")
    if cuda:
        return "cu" + "".join(cuda.split(".")[:2])
    hip = str(torch.get("hipVersion") or "")
    if hip:
        parts = hip.split(".")
        return "rocm" + ".".join(parts[:2])
    if torch.get("mpsAvailable") or machine.get("accelerator") == "apple-mps":
        return "pypi"
    return "cpu"


def _ready_summary(status: dict[str, Any]) -> str:
    packages = status["packages"]
    torch = status["torch"]
    if torch.get("cudaAvailable"):
        backend = f"CUDA {torch.get('cudaVersion') or ''}".strip()
    elif torch.get("hipVersion"):
        backend = f"ROCm {torch['hipVersion']}"
    elif torch.get("mpsAvailable"):
        backend = "Apple MPS"
    else:
        backend = "CPU"
    return (
        "Runtime base ready: "
        f"torch {packages['torch']} ({backend}), numpy {packages['numpy']}, "
        f"scikit-learn {packages['scikit-learn']}."
    )


def _report(reporter: Callable[[str], None] | None, message: str) -> None:
    if reporter:
        reporter(message)
