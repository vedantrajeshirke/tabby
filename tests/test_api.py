from fastapi.testclient import TestClient

from api.main import app
from core import config


def test_status_reports_mode_without_secrets(monkeypatch):
    monkeypatch.setenv("EXTRACTION_BACKEND", "mock")
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setattr(config.shutil, "which", lambda _: None)
    monkeypatch.setenv("TESSERACT_CMD", "")
    response = TestClient(app).get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["mock_mode"] is True
    assert body["auth_mode"] == "local"
    assert body["tesseract_available"] is False
    assert "brew install tesseract" in body["tesseract_help"]
    assert response.headers["cache-control"] == "no-store"


def test_unknown_route_is_404_with_no_internals():
    response = TestClient(app).get("/api/nope")
    assert response.status_code == 404
    assert "Traceback" not in response.text
