import pytest
from fastapi.testclient import TestClient

from kis_auto_trading.main import app


@pytest.fixture(autouse=True)
def configure_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    database_url = "postgresql+asyncpg://user:password@localhost/database"
    monkeypatch.setenv("IDENTITY_DATABASE_URL", database_url)
    monkeypatch.setenv("ACCOUNT_SHARD_1_DATABASE_URL", database_url)


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


def test_login_resolves_session_store_before_calling_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/identity/login",
            json={"email": "user@example.com", "password": "not-a-secret"},
        )

    assert response.status_code == 500
