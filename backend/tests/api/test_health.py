from fastapi.testclient import TestClient

from data_workbench.api.app import create_app
from data_workbench.core.config import AppConfig


def test_health_requires_session_token(tmp_path):
    app = create_app(AppConfig(workspace=tmp_path), token="secret")
    client = TestClient(app)
    assert client.get("/api/health").status_code == 401
    response = client.get("/api/health", headers={"X-Session-Token": "secret"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
