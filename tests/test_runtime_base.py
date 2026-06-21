from __future__ import annotations

import json
import tomllib
from pathlib import Path
from types import SimpleNamespace

from harnessing_ts import runtime_base
from harnessing_ts.workspace_runtime import _ensure_pyproject, _uv_sync_env


def _machine() -> dict[str, str]:
    return {
        "system": "Linux",
        "release": "test",
        "machine": "x86_64",
        "accelerator": "nvidia-cuda",
        "acceleratorDetail": "Test GPU",
    }


def test_prepare_runtime_base_records_resolved_packages_and_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_base.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(runtime_base, "detect_machine", _machine)

    def fake_run(command, **kwargs):
        if command[:2] == ["/usr/bin/uv", "venv"]:
            (tmp_path / ".venv" / "bin").mkdir(parents=True)
            (tmp_path / ".venv" / "bin" / "python").touch()
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:3] == ["/usr/bin/uv", "pip", "install"]:
            assert "sktime>=0.35" in command
            assert "pandas>=2.2" in command
            assert "scipy>=1.12" in command
            assert "matplotlib>=3.8" in command
            assert "python-docx>=1.1.2" in command
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        payload = {
            "packages": {
                "torch": "2.8.0",
                "python-docx": "1.2.0",
                "numpy": "2.2.6",
                "pandas": "2.3.1",
                "scipy": "1.16.1",
                "scikit-learn": "1.7.1",
                "matplotlib": "3.10.5",
                "sktime": "0.39.0",
            },
            "torch": {"cudaAvailable": True, "cudaVersion": "12.8", "hipVersion": None, "mpsAvailable": False, "deviceCount": 1},
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(runtime_base.subprocess, "run", fake_run)
    messages: list[str] = []
    status = runtime_base.prepare_runtime_base(tmp_path, reporter=messages.append)

    assert status["state"] == "ready"
    assert status["packages"]["torch"] == "2.8.0"
    assert status["torch"]["cudaAvailable"] is True
    assert any("CUDA 12.8" in message for message in messages)
    assert "--torch-backend auto" in status["commands"][1]
    assert status["torchBackend"] == "cu128"
    assert (tmp_path / "uv-cache").as_posix() == status["cache"]
    assert status["packages"]["sktime"] == "0.39.0"


def test_new_workspace_pins_and_reuses_runtime_base(tmp_path, monkeypatch):
    base_root = tmp_path / "base"
    workspace = tmp_path / "workspace"
    base = {
        "root": str(base_root),
        "cache": str(base_root / "uv-cache"),
        "packages": {
            "torch": "2.8.0",
            "python-docx": "1.2.0",
            "numpy": "2.2.6",
            "pandas": "2.3.1",
            "scipy": "1.16.1",
            "scikit-learn": "1.7.1",
            "matplotlib": "3.10.5",
            "sktime": "0.39.0",
        },
        "torchBackend": "cu128",
    }
    workspace.mkdir()
    monkeypatch.delenv("UV_TORCH_BACKEND", raising=False)

    assert _ensure_pyproject(workspace, base) is True
    pyproject = (workspace / "pyproject.toml").read_text(encoding="utf-8")
    parsed = tomllib.loads(pyproject)
    assert '"torch==2.8.0"' in pyproject
    assert '"python-docx==1.2.0"' in pyproject
    assert '"numpy==2.2.6"' in pyproject
    assert '"pandas==2.3.1"' in pyproject
    assert '"scipy==1.16.1"' in pyproject
    assert '"scikit-learn==1.7.1"' in pyproject
    assert '"matplotlib==3.10.5"' in pyproject
    assert '"sktime==0.39.0"' in pyproject
    assert '"python-docx>=1.1.2"' not in pyproject
    assert '"numpy>=1.26"' not in pyproject
    assert '"pandas>=2.2"' not in pyproject
    assert '"scipy>=1.12"' not in pyproject
    assert '"scikit-learn>=1.4"' not in pyproject
    assert '"matplotlib>=3.8"' not in pyproject
    assert '"sktime>=0.35"' not in pyproject
    assert 'url = "https://download.pytorch.org/whl/cu128"' in pyproject
    assert parsed["tool"]["uv"]["sources"]["torch"]["index"] == "pytorch-cu128"

    monkeypatch.setenv("VIRTUAL_ENV", "/unrelated")
    env = _uv_sync_env(workspace, base)
    assert "VIRTUAL_ENV" not in env
    assert env["UV_CACHE_DIR"] == str(base_root / "uv-cache")
    assert "UV_TORCH_BACKEND" not in env


def test_runtime_base_is_rejected_for_wrong_python_or_machine(tmp_path, monkeypatch):
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    status = {
        "state": "ready",
        "venv": str(tmp_path / ".venv"),
        "pythonVersion": "3.11",
        "machine": _machine(),
        "packages": {
            "torch": "2.8.0",
            "python-docx": "1.2.0",
            "numpy": "2.2.6",
            "pandas": "2.3.1",
            "scipy": "1.16.1",
            "scikit-learn": "1.7.1",
            "matplotlib": "3.10.5",
            "sktime": "0.39.0",
        },
    }
    (tmp_path / runtime_base.STATUS_FILE).write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setattr(runtime_base, "detect_machine", _machine)

    assert runtime_base.read_runtime_base(tmp_path, python_version="3.11") is not None
    assert runtime_base.read_runtime_base(tmp_path, python_version="3.12") is None
    monkeypatch.setattr(runtime_base, "detect_machine", lambda: {**_machine(), "machine": "aarch64"})
    assert runtime_base.read_runtime_base(tmp_path, python_version="3.11") is None
