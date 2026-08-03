import pytest
from fastapi.testclient import TestClient

from kis_auto_trading.main import app


def test_identity_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "post" in paths["/api/identity/signup"]
    assert "post" in paths["/api/identity/login"]


def test_unimplemented_signup_is_not_reported_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/identity/signup",
            json={"email": "user@example.com", "password": "not-a-secret"},
        )

    assert response.status_code == 500
