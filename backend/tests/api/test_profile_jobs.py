from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from data_workbench.api.app import create_app
from data_workbench.core.config import AppConfig

HEADERS = {"X-Session-Token": "secret"}
CSV_BYTES = b"customer_id,amount\nc1,10\nc2,20\nc3,30\n,40\n"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        AppConfig(workspace=tmp_path, memory_limit="512MB", max_threads=1),
        token="secret",
    )
    # Keep one client (and one event loop) alive across requests so background
    # jobs survive between polls.
    with TestClient(app) as live_client:
        yield live_client


def upload_session(client: TestClient, content: bytes = CSV_BYTES) -> str:
    response = client.post(
        "/api/sessions",
        params={"filename": "customers.csv"},
        headers=HEADERS,
        content=content,
    )
    assert response.status_code == 200
    session_id: str = response.json()["id"]
    return session_id


def wait_for_job(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}", headers=HEADERS)
        assert response.status_code == 200
        job = response.json()
        if job["state"] in {"succeeded", "failed", "cancelled"}:
            return dict(job)
        time.sleep(0.05)
    raise AssertionError("job did not reach a terminal state in time")


def test_profile_job_persists_profile_and_findings(client: TestClient) -> None:
    session_id = upload_session(client)

    started = client.post(f"/api/sessions/{session_id}/profile", headers=HEADERS)
    assert started.status_code == 202
    job = wait_for_job(client, started.json()["job_id"])
    assert job == {
        "id": started.json()["job_id"],
        "kind": "profile",
        "state": "succeeded",
        "error_code": None,
    }

    saved = client.get(f"/api/sessions/{session_id}/profile", headers=HEADERS)
    assert saved.status_code == 200
    profile = saved.json()["profile"]
    assert profile["row_count"] == 4
    assert profile["source_fingerprint"] == client.get(
        f"/api/sessions/{session_id}", headers=HEADERS
    ).json()["sha256"]
    column_names = [column["name"] for column in profile["columns"]]
    assert {"customer_id", "amount"} <= set(column_names)
    assert isinstance(saved.json()["findings"], list)

    session = client.get(f"/api/sessions/{session_id}", headers=HEADERS)
    assert session.json()["state"] == "profiled"


def test_job_events_stream_stages_in_order(client: TestClient) -> None:
    session_id = upload_session(client)
    job_id = client.post(
        f"/api/sessions/{session_id}/profile", headers=HEADERS
    ).json()["job_id"]
    wait_for_job(client, job_id)

    response = client.get(f"/api/jobs/{job_id}/events", headers=HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [event["sequence"] for event in events] == list(
        range(1, len(events) + 1)
    )
    stages = [event["stage"] for event in events]
    assert stages[0] == "inspect"
    assert stages[-1] == "persist"
    assert {"profile", "findings"} <= set(stages)


def test_invalid_input_fails_with_sanitized_error_code(client: TestClient) -> None:
    session_id = upload_session(client, content=b"\x00\xff\x00\xfe")

    job_id = client.post(
        f"/api/sessions/{session_id}/profile", headers=HEADERS
    ).json()["job_id"]
    job = wait_for_job(client, job_id)

    assert job["state"] == "failed"
    assert job["error_code"] == "invalid_input"
    missing = client.get(f"/api/sessions/{session_id}/profile", headers=HEADERS)
    assert missing.status_code == 404


def test_profile_can_be_cancelled_and_retried(client: TestClient) -> None:
    session_id = upload_session(client)

    first = client.post(
        f"/api/sessions/{session_id}/profile", headers=HEADERS
    ).json()["job_id"]
    cancelled = client.delete(f"/api/jobs/{first}", headers=HEADERS)
    assert cancelled.status_code == 202
    assert wait_for_job(client, first)["state"] in {"cancelled", "succeeded"}

    retry = client.post(
        f"/api/sessions/{session_id}/profile", headers=HEADERS
    ).json()["job_id"]
    assert wait_for_job(client, retry)["state"] == "succeeded"


def test_job_routes_reject_unknown_ids_and_missing_auth(client: TestClient) -> None:
    assert client.get("/api/jobs/missing", headers=HEADERS).status_code == 404
    assert client.delete("/api/jobs/missing", headers=HEADERS).status_code == 404
    assert (
        client.get("/api/jobs/missing/events", headers=HEADERS).status_code == 404
    )
    assert client.get("/api/jobs/missing").status_code == 401
    assert (
        client.post(
            "/api/sessions/00000000000000000000000000000000/profile",
            headers=HEADERS,
        ).status_code
        == 404
    )
