from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def skip_real_workspace_uv_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not materialize a full uv environment for every tmp workspace."""
    monkeypatch.setenv("TS_HARNESS_SKIP_WORKSPACE_UV", "true")
