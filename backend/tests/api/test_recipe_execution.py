from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from data_workbench.api.app import create_app
from data_workbench.core.config import AppConfig

HEADERS = {"X-Session-Token": "secret"}
CSV_BYTES = b"customer_id,amount\nc1,RM 1200\nc2,x\nc3,10\nc1,RM 1200\n"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        AppConfig(workspace=tmp_path, memory_limit="512MB", max_threads=1),
        token="secret",
    )
    with TestClient(app) as live_client:
        yield live_client


def upload_session(client: TestClient) -> tuple[str, str]:
    response = client.post(
        "/api/sessions",
        params={"filename": "customers.csv"},
        headers=HEADERS,
        content=CSV_BYTES,
    )
    assert response.status_code == 200
    return response.json()["id"], response.json()["sha256"]


def cast_recipe(fingerprint: str, on_error: str) -> dict[str, object]:
    return {
        "recipe_version": 1,
        "source_fingerprint": fingerprint,
        "steps": [
            {
                "id": "c",
                "operation": "cast_number",
                "columns": ["amount"],
                "target": "integer",
                "on_error": on_error,
            }
        ],
    }


def wait_for_job(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
        if job["state"] in {"succeeded", "failed", "cancelled"}:
            return dict(job)
        time.sleep(0.05)
    raise AssertionError("job did not reach a terminal state in time")


def test_preview_reports_changes_without_writing_outputs(
    client: TestClient, tmp_path: Path
) -> None:
    session_id, fingerprint = upload_session(client)

    response = client.post(
        f"/api/sessions/{session_id}/recipe/preview",
        headers=HEADERS,
        json={"recipe": cast_recipe(fingerprint, "quarantine")},
    )

    assert response.status_code == 200
    preview = response.json()
    assert len(preview["before_rows"]) == 4
    assert len(preview["after_rows"]) == 3
    assert any("quarantined" in note for note in preview["validation_failures"])
    assert not (tmp_path / session_id / "outputs").exists()


def test_execution_requires_approval_and_matching_fingerprint(
    client: TestClient,
) -> None:
    session_id, fingerprint = upload_session(client)

    unapproved = client.post(
        f"/api/sessions/{session_id}/recipe/execute",
        headers=HEADERS,
        json={"recipe": cast_recipe(fingerprint, "preserve")},
    )
    mismatched = client.post(
        f"/api/sessions/{session_id}/recipe/execute",
        headers=HEADERS,
        json={"recipe": cast_recipe("0" * 64, "preserve"), "approved": True},
    )

    assert unapproved.status_code == 400
    assert "approved=true" in unapproved.json()["detail"]
    assert mismatched.status_code == 409
    assert client.get(
        f"/api/sessions/{session_id}/execution", headers=HEADERS
    ).status_code == 404


def test_approved_execution_persists_result_and_outputs(
    client: TestClient, tmp_path: Path
) -> None:
    session_id, fingerprint = upload_session(client)

    started = client.post(
        f"/api/sessions/{session_id}/recipe/execute",
        headers=HEADERS,
        json={
            "recipe": cast_recipe(fingerprint, "quarantine"),
            "approved": True,
        },
    )
    assert started.status_code == 202
    job = wait_for_job(client, started.json()["job_id"])
    assert job["state"] == "succeeded"

    execution = client.get(
        f"/api/sessions/{session_id}/execution", headers=HEADERS
    )
    assert execution.status_code == 200
    result = execution.json()
    assert result["input_rows"] == 4
    assert result["output_rows"] == 3
    assert result["quarantined_rows"] == 1
    assert Path(result["cleaned_path"]).exists()
    assert Path(result["quarantine_path"]).exists()
    source = tmp_path / session_id / "source.bin"
    assert source.read_bytes() == CSV_BYTES

    retry = client.post(
        f"/api/sessions/{session_id}/recipe/execute",
        headers=HEADERS,
        json={"recipe": cast_recipe(fingerprint, "preserve"), "approved": True},
    )
    assert wait_for_job(client, retry.json()["job_id"])["state"] == "succeeded"
    assert client.get(
        f"/api/sessions/{session_id}/execution", headers=HEADERS
    ).json()["output_rows"] == 4


def test_invalid_recipes_are_rejected_up_front(client: TestClient) -> None:
    session_id, fingerprint = upload_session(client)

    unknown_operation = client.post(
        f"/api/sessions/{session_id}/recipe/preview",
        headers=HEADERS,
        json={
            "recipe": {
                "recipe_version": 1,
                "source_fingerprint": fingerprint,
                "steps": [{"id": "p", "operation": "python", "code": "1"}],
            }
        },
    )
    missing_session = client.post(
        "/api/sessions/00000000000000000000000000000000/recipe/preview",
        headers=HEADERS,
        json={"recipe": cast_recipe(fingerprint, "preserve")},
    )
    unauthenticated = client.post(
        f"/api/sessions/{session_id}/recipe/preview",
        json={"recipe": cast_recipe(fingerprint, "preserve")},
    )

    assert unknown_operation.status_code == 422
    assert missing_session.status_code == 404
    assert unauthenticated.status_code == 401
