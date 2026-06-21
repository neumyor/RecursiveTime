from __future__ import annotations

from types import SimpleNamespace

from harnessing_ts import server_setup


def test_setup_server_combines_frontend_build_and_runtime_base(tmp_path, monkeypatch) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    monkeypatch.setattr(server_setup, "project_root", lambda: tmp_path)
    monkeypatch.setattr(server_setup, "frontend_root", lambda: frontend)
    monkeypatch.setattr(server_setup.shutil, "which", lambda name: "/usr/bin/bun" if name == "bun" else None)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(server_setup.subprocess, "run", fake_run)
    monkeypatch.setattr(server_setup, "prepare_runtime_base", lambda **kwargs: {
        "state": "ready",
        "root": str(tmp_path / ".runtime-base"),
    })
    messages: list[str] = []

    result = server_setup.setup_server(reporter=messages.append)

    assert result["state"] == "ready"
    assert commands == [
        ["/usr/bin/bun", "install", "--frozen-lockfile"],
        ["/usr/bin/bun", "run", "build"],
    ]
    assert result["frontend"]["state"] == "ready"
    assert result["runtimeBase"]["state"] == "ready"
    assert any("automatically" in message and "TS_HARNESS_WORKSPACE" in message for message in messages)


def test_setup_server_fails_with_actionable_message_when_bun_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server_setup, "project_root", lambda: tmp_path)
    monkeypatch.setattr(server_setup, "frontend_root", lambda: tmp_path / "frontend")
    monkeypatch.setattr(server_setup.shutil, "which", lambda _name: None)

    result = server_setup.setup_server(reporter=None)

    assert result["state"] == "failed"
    assert "install Bun" in result["message"]


def test_setup_server_supports_explicit_partial_setup(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server_setup, "project_root", lambda: tmp_path)
    result = server_setup.setup_server(skip_frontend=True, skip_runtime_base=True, reporter=None)

    assert result["state"] == "ready"
    assert result["frontend"]["state"] == "skipped"
    assert result["runtimeBase"]["state"] == "skipped"
