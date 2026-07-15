from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data_workbench.api.app import create_app
from data_workbench.cli import build_server, reserve_ephemeral_port
from data_workbench.core.config import AppConfig
from data_workbench.core.security import (
    Redactor,
    redact_mapping,
    validate_loopback_host,
)

HEADERS = {"X-Session-Token": "secret"}


def test_launcher_rejects_non_loopback_hosts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        build_server(host="0.0.0.0", workspace=tmp_path, open_browser=False)

    server = build_server(
        host="127.0.0.1", workspace=tmp_path, open_browser=False
    )
    assert server.config.host == "127.0.0.1"
    assert server.config.port > 0

    for host in ("localhost", "127.0.0.1", "::1"):
        assert validate_loopback_host(host) == host
    with pytest.raises(ValueError, match="loopback"):
        validate_loopback_host("192.168.1.5")


def test_untrusted_origins_are_rejected(tmp_path: Path) -> None:
    app = create_app(
        AppConfig(workspace=tmp_path, allowed_origin="http://127.0.0.1:8765"),
        token="secret",
    )
    client = TestClient(app)

    trusted = client.get(
        "/api/health",
        headers={**HEADERS, "Origin": "http://127.0.0.1:8765"},
    )
    untrusted = client.get(
        "/api/health",
        headers={**HEADERS, "Origin": "https://example.com"},
    )
    absent = client.get("/api/health", headers=HEADERS)

    assert trusted.status_code == 200
    assert untrusted.status_code == 403
    assert untrusted.json() == {"detail": "origin not allowed"}
    assert absent.status_code == 200


def test_logs_redact_samples_and_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger="data_workbench"):
        Redactor().log_error(
            {
                "sample": "alice@example.com",
                "api_key": "secret-key",
                "nested": {"example_value": "raw-cell"},
                "stage": "profile",
            }
        )

    assert "alice@example.com" not in caplog.text
    assert "secret-key" not in caplog.text
    assert "raw-cell" not in caplog.text
    assert "profile" in caplog.text
    assert redact_mapping({"token": "x", "rows": 4}) == {
        "token": "[redacted]",
        "rows": 4,
    }


def test_bundled_ui_is_served_from_static_mount(tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        "<!DOCTYPE html><title>Workbench</title>", encoding="utf-8"
    )
    app = create_app(
        AppConfig(workspace=tmp_path / "sessions"),
        token="secret",
        static_dir=static,
    )
    client = TestClient(app)

    page = client.get("/")
    unauthenticated_api = client.get("/api/health")

    assert page.status_code == 200
    assert "Workbench" in page.text
    assert unauthenticated_api.status_code == 401


def test_ephemeral_ports_are_loopback_bound(tmp_path: Path) -> None:
    del tmp_path
    first = reserve_ephemeral_port("127.0.0.1")
    assert 0 < first < 65536
