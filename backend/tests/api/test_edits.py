from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from data_workbench.api.app import create_app
from data_workbench.core.config import AppConfig

HEADERS = {"X-Session-Token": "secret"}
CSV_BYTES = b"customer_id,name,city\nc1, Ada ,kul\nc2,lin,\nc3,N/A,jhb\n"


def upload_session(client: TestClient) -> str:
    response = client.post(
        "/api/sessions",
        params={"filename": "customers.csv"},
        headers=HEADERS,
        content=CSV_BYTES,
    )
    assert response.status_code == 200
    session_id: str = response.json()["id"]
    return session_id


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(
        AppConfig(workspace=tmp_path, memory_limit="512MB", max_threads=1),
        token="secret",
    )
    return TestClient(app)


def test_preview_parses_command_and_reports_changes(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    session_id = upload_session(client)

    response = client.post(
        f"/api/sessions/{session_id}/edits/preview",
        headers=HEADERS,
        json={"command": "replace 'N/A' with null in column name"},
    )

    assert response.status_code == 200
    preview = response.json()
    assert preview["command"]["operation"] == "replace_value"
    assert preview["columns_before"] == ["customer_id", "name", "city"]
    assert preview["affected_row_count"] == 1
    assert preview["samples"] == [{"before": "N/A", "after": None}]


def test_apply_requires_explicit_approval(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    session_id = upload_session(client)

    response = client.post(
        f"/api/sessions/{session_id}/edits",
        headers=HEADERS,
        json={"command": "drop column city"},
    )

    assert response.status_code == 400
    assert "approved=true" in response.json()["detail"]
    history = client.get(f"/api/sessions/{session_id}/edits", headers=HEADERS)
    assert history.json() == []


def test_approved_edits_apply_chain_and_record_history(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    session_id = upload_session(client)

    first = client.post(
        f"/api/sessions/{session_id}/edits",
        headers=HEADERS,
        json={"command": "trim column name", "approved": True},
    )
    second = client.post(
        f"/api/sessions/{session_id}/edits",
        headers=HEADERS,
        json={
            "command": "rename column customer_id to customer",
            "approved": True,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["sequence"] == 2

    preview = client.post(
        f"/api/sessions/{session_id}/edits/preview",
        headers=HEADERS,
        json={"command": "uppercase column name"},
    )
    assert preview.status_code == 200
    assert preview.json()["columns_before"] == ["customer", "name", "city"]
    assert {sample["before"] for sample in preview.json()["samples"]} == {
        "Ada",
        "lin",
    }

    history = client.get(f"/api/sessions/{session_id}/edits", headers=HEADERS)
    assert [entry["sequence"] for entry in history.json()] == [1, 2]


def test_rows_preview_reflects_applied_edits(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    session_id = upload_session(client)

    initial = client.get(f"/api/sessions/{session_id}/rows", headers=HEADERS)
    assert initial.status_code == 200
    body = initial.json()
    assert body["columns"] == ["customer_id", "name", "city"]
    assert body["total_rows"] == 3
    assert body["rows"][0] == ["c1", " Ada ", "kul"]

    preview = client.post(
        f"/api/sessions/{session_id}/edits/preview",
        headers=HEADERS,
        json={"command": "move column city before name"},
    )
    assert preview.status_code == 200
    assert preview.json()["columns_after"] == ["customer_id", "city", "name"]
    assert preview.json()["affected_row_count"] == 0

    applied = client.post(
        f"/api/sessions/{session_id}/edits",
        headers=HEADERS,
        json={"command": "move column name to end", "approved": True},
    )
    assert applied.status_code == 200
    assert applied.json()["command"]["operation"] == "move_column"

    after = client.get(
        f"/api/sessions/{session_id}/rows",
        headers=HEADERS,
        params={"limit": 2},
    )
    assert after.json()["columns"] == ["customer_id", "city", "name"]
    assert len(after.json()["rows"]) == 2


def test_edit_errors_map_to_bad_request(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    session_id = upload_session(client)

    unsupported = client.post(
        f"/api/sessions/{session_id}/edits/preview",
        headers=HEADERS,
        json={"command": "make it pretty"},
    )
    unknown_column = client.post(
        f"/api/sessions/{session_id}/edits/preview",
        headers=HEADERS,
        json={"command": "drop column missing"},
    )

    assert unsupported.status_code == 400
    assert "Supported commands" in unsupported.json()["detail"]
    assert unknown_column.status_code == 400
    assert "missing" in unknown_column.json()["detail"]


def test_edit_routes_require_session_and_token(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    missing = client.post(
        "/api/sessions/00000000000000000000000000000000/edits/preview",
        headers=HEADERS,
        json={"command": "drop column city"},
    )
    unauthenticated = client.post(
        "/api/sessions/00000000000000000000000000000000/edits/preview",
        json={"command": "drop column city"},
    )

    assert missing.status_code == 404
    assert unauthenticated.status_code == 401
