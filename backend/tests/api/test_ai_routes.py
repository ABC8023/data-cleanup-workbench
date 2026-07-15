from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from data_workbench.api.app import create_app
from data_workbench.core.config import AppConfig

HEADERS = {"X-Session-Token": "secret"}
CSV_BYTES = b"customer_id,amount\nc1,10\nc2,20\n,30\n"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        AppConfig(workspace=tmp_path, memory_limit="512MB", max_threads=1),
        token="secret",
    )
    with TestClient(app) as live_client:
        yield live_client


def profiled_session(client: TestClient) -> str:
    upload = client.post(
        "/api/sessions",
        params={"filename": "customers.csv"},
        headers=HEADERS,
        content=CSV_BYTES,
    ).json()
    session_id: str = upload["id"]
    job_id = client.post(
        f"/api/sessions/{session_id}/profile", headers=HEADERS
    ).json()["job_id"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()["state"]
        if state == "succeeded":
            return session_id
        assert state in {"queued", "running"}
        time.sleep(0.05)
    raise AssertionError("profile job did not finish")


def test_two_phase_ai_flow_defaults_to_disabled_with_fallback(
    client: TestClient,
) -> None:
    session_id = profiled_session(client)

    preview = client.post(
        f"/api/sessions/{session_id}/ai/dictionary/preview",
        headers=HEADERS,
        json={"selected_samples": {}},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["provider"] == "disabled"
    assert all("examples" not in column for column in body["payload"]["columns"])

    approved = client.post(
        f"/api/sessions/{session_id}/ai/dictionary/approve",
        headers=HEADERS,
        json={"preview_id": body["id"]},
    )
    assert approved.status_code == 200
    attempt = approved.json()
    assert attempt["suggestion"] is None
    assert attempt["error"]["code"] == "disabled"
    assert attempt["fallback"]["columns"]


def test_ai_routes_require_profile_session_and_token(client: TestClient) -> None:
    upload = client.post(
        "/api/sessions",
        params={"filename": "customers.csv"},
        headers=HEADERS,
        content=CSV_BYTES,
    ).json()

    unprofiled = client.post(
        f"/api/sessions/{upload['id']}/ai/dictionary/preview",
        headers=HEADERS,
        json={},
    )
    missing = client.post(
        "/api/sessions/00000000000000000000000000000000/ai/dictionary/preview",
        headers=HEADERS,
        json={},
    )
    unauthenticated = client.post(
        f"/api/sessions/{upload['id']}/ai/dictionary/preview", json={}
    )

    assert unprofiled.status_code == 409
    assert missing.status_code == 404
    assert unauthenticated.status_code == 401
