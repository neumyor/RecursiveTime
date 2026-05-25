from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def frontend_root() -> Path:
    return project_root() / "frontend"


def default_workspace_path() -> Path:
    configured = os.getenv("TS_HARNESS_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".harnessingts" / "workspaces" / "default").resolve()
