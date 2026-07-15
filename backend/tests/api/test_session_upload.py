import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from fastapi.testclient import TestClient

from data_workbench.api.app import create_app
from data_workbench.api.routes import sessions
from data_workbench.core.config import AppConfig
from data_workbench.storage.session_repository import SessionRepository


def test_upload_sanitizes_filename_and_get_returns_staged_manifest(tmp_path):
    app = create_app(AppConfig(workspace=tmp_path, max_file_bytes=16), token="secret")
    client = TestClient(app)
    headers = {"X-Session-Token": "secret"}

    response = client.post(
        "/api/sessions",
        params={"filename": "../../sample.csv"},
        headers=headers,
        content=b"a,b\n1,2\n",
    )

    assert response.status_code == 200
    manifest = response.json()
    assert manifest["filename"] == "sample.csv"
    assert manifest["state"] == "staged"
    source_path = Path(manifest["source_path"])
    assert source_path.parent.parent == tmp_path
    assert source_path.read_bytes() == b"a,b\n1,2\n"

    fetched = client.get(f"/api/sessions/{manifest['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json() == manifest


def test_upload_requires_content_length(tmp_path):
    app = create_app(AppConfig(workspace=tmp_path, max_file_bytes=16), token="secret")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/sessions",
        params={"filename": "sample.csv"},
        headers={"X-Session-Token": "secret"},
        content=iter([b"data"]),
    )

    assert response.status_code == 411
    assert response.json() == {"detail": "Content-Length is required"}


def test_upload_rejects_declared_size_above_limit(tmp_path):
    app = create_app(AppConfig(workspace=tmp_path, max_file_bytes=3), token="secret")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/sessions",
        params={"filename": "large.csv"},
        headers={"X-Session-Token": "secret"},
        content=b"data",
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "file exceeds 5 GB limit"}
    assert list(tmp_path.iterdir()) == []


def test_upload_requires_twice_the_declared_size_in_free_space(
    tmp_path,
    monkeypatch,
):
    app = create_app(AppConfig(workspace=tmp_path, max_file_bytes=16), token="secret")
    client = TestClient(app)
    monkeypatch.setattr("shutil.disk_usage", lambda _: SimpleNamespace(free=7))

    response = client.post(
        "/api/sessions",
        params={"filename": "sample.csv"},
        headers={"X-Session-Token": "secret"},
        content=b"data",
    )

    assert response.status_code == 507
    assert response.json() == {"detail": "insufficient local disk space"}
    assert list(tmp_path.iterdir()) == []


def test_upload_maps_stream_size_mismatch_to_bad_request(tmp_path):
    app = create_app(AppConfig(workspace=tmp_path, max_file_bytes=16), token="secret")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/sessions",
        params={"filename": "sample.csv"},
        headers={"X-Session-Token": "secret", "Content-Length": "4"},
        content=b"123",
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "stream size did not match Content-Length"
    }
    assert list(tmp_path.iterdir()) == []


def test_get_rejects_session_id_path_traversal(tmp_path):
    app = create_app(AppConfig(workspace=tmp_path, max_file_bytes=16), token="secret")
    app.state.session_repository = SessionRepository(
        tmp_path / "sessions",
        max_file_bytes=16,
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "session.json").write_text(
        json.dumps(
            {
                "id": "leaked",
                "filename": "outside.csv",
                "size_bytes": 0,
                "sha256": "0" * 64,
                "source_path": str(outside / "source.bin"),
                "state": "staged",
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(app)

    response = client.get(
        "/api/sessions/..%5Coutside",
        headers={"X-Session-Token": "secret"},
    )

    assert response.status_code == 404


def test_session_routes_require_authentication(tmp_path):
    app = create_app(AppConfig(workspace=tmp_path, max_file_bytes=16), token="secret")
    client = TestClient(app)

    upload = client.post(
        "/api/sessions",
        params={"filename": "sample.csv"},
        content=b"data",
    )
    fetch = client.get("/api/sessions/00000000000000000000000000000000")

    assert upload.status_code == 401
    assert fetch.status_code == 401


def test_upload_normalizes_windows_filename_separators_on_posix(
    tmp_path,
    monkeypatch,
):
    app = create_app(AppConfig(workspace=tmp_path, max_file_bytes=16), token="secret")
    client = TestClient(app)
    monkeypatch.setattr(sessions, "Path", PurePosixPath)

    response = client.post(
        "/api/sessions",
        params={"filename": r"..\..\sample.csv"},
        headers={"X-Session-Token": "secret"},
        content=b"data",
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "sample.csv"
