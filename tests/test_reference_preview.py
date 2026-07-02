import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient


def test_reference_preview_serves_reference_inline(tmp_path, monkeypatch):
    from harnessing_ts.server import create_app

    references = tmp_path / "references"
    references.mkdir(parents=True)
    (references / "paper.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("TS_HARNESS_WORKSPACE", str(tmp_path))

    client = TestClient(create_app())
    response = client.get("/api/references/preview?path=references/paper.pdf")

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["content-type"].startswith("application/pdf")


def test_reference_preview_rejects_paths_outside_references(tmp_path, monkeypatch):
    from harnessing_ts.server import create_app

    (tmp_path / "user").mkdir(parents=True)
    (tmp_path / "user" / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setenv("TS_HARNESS_WORKSPACE", str(tmp_path))

    client = TestClient(create_app())
    response = client.get("/api/references/preview?path=user/secret.txt")

    assert response.status_code == 403


def test_reference_delete_removes_reference_file(tmp_path, monkeypatch):
    from harnessing_ts.server import create_app

    references = tmp_path / "references"
    references.mkdir(parents=True)
    target = references / "paper.pdf"
    target.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("TS_HARNESS_WORKSPACE", str(tmp_path))

    client = TestClient(create_app())
    response = client.request("DELETE", "/api/references", json={"path": "references/paper.pdf"})

    assert response.status_code == 200
    assert response.json()["deleted"]["path"] == "references/paper.pdf"
    assert not target.exists()


def test_reference_delete_rejects_paths_outside_references(tmp_path, monkeypatch):
    from harnessing_ts.server import create_app

    (tmp_path / "user").mkdir(parents=True)
    (tmp_path / "user" / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setenv("TS_HARNESS_WORKSPACE", str(tmp_path))

    client = TestClient(create_app())
    response = client.request("DELETE", "/api/references", json={"path": "user/secret.txt"})

    assert response.status_code == 403
    assert (tmp_path / "user" / "secret.txt").exists()
