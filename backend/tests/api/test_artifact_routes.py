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


def wait_for_job(client: TestClient, job_id: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
        if job["state"] in {"succeeded", "failed", "cancelled"}:
            assert job["state"] == "succeeded", job
            return
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def completed_session(client: TestClient) -> str:
    upload = client.post(
        "/api/sessions",
        params={"filename": "customers.csv"},
        headers=HEADERS,
        content=CSV_BYTES,
    ).json()
    session_id: str = upload["id"]
    wait_for_job(
        client,
        client.post(
            f"/api/sessions/{session_id}/profile", headers=HEADERS
        ).json()["job_id"],
    )
    recipe = {
        "recipe_version": 1,
        "source_fingerprint": upload["sha256"],
        "steps": [
            {
                "id": "c",
                "operation": "cast_number",
                "columns": ["amount"],
                "target": "integer",
                "on_error": "quarantine",
            }
        ],
    }
    wait_for_job(
        client,
        client.post(
            f"/api/sessions/{session_id}/recipe/execute",
            headers=HEADERS,
            json={"recipe": recipe, "approved": True},
        ).json()["job_id"],
    )
    return session_id


def test_artifact_build_list_download_and_dictionary_flow(
    client: TestClient,
) -> None:
    session_id = completed_session(client)

    premature = client.get(f"/api/sessions/{session_id}/artifacts", headers=HEADERS)
    assert premature.status_code == 404

    saved = client.put(
        f"/api/sessions/{session_id}/dictionary",
        headers=HEADERS,
        json={"descriptions": {"customer_id": "Customer key"}},
    )
    assert saved.status_code == 200
    assert client.get(
        f"/api/sessions/{session_id}/dictionary", headers=HEADERS
    ).json() == {"customer_id": "Customer key"}

    built = client.post(f"/api/sessions/{session_id}/artifacts", headers=HEADERS)
    assert built.status_code == 200
    manifest = built.json()
    assert manifest["state"] == "complete"
    assert manifest["recipe_hash"]
    kinds = {record["kind"] for record in manifest["artifacts"]}
    assert {"cleaned", "quarantine", "recipe", "report_json", "dictionary_md"} <= kinds

    listed = client.get(f"/api/sessions/{session_id}/artifacts", headers=HEADERS)
    assert listed.json() == manifest

    download = client.get(
        f"/api/sessions/{session_id}/artifacts/dictionary_md", headers=HEADERS
    )
    assert download.status_code == 200
    assert "Customer key" in download.text
    assert 'filename="dictionary.md"' in download.headers["content-disposition"]

    assert (
        client.get(
            f"/api/sessions/{session_id}/artifacts/../secrets", headers=HEADERS
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/sessions/{session_id}/artifacts/missing", headers=HEADERS
        ).status_code
        == 404
    )
    assert client.post(f"/api/sessions/{session_id}/artifacts").status_code == 401


def test_artifact_build_requires_execution(client: TestClient) -> None:
    upload = client.post(
        "/api/sessions",
        params={"filename": "customers.csv"},
        headers=HEADERS,
        content=CSV_BYTES,
    ).json()

    response = client.post(
        f"/api/sessions/{upload['id']}/artifacts", headers=HEADERS
    )

    assert response.status_code == 409
    assert "executed" in response.json()["detail"]
