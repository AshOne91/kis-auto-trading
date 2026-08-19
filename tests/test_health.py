import pytest
from fastapi.testclient import TestClient

from kis_auto_trading.main import app


def test_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("KIS_API_URL", "https://example.invalid")
    monkeypatch.setenv("KIS_APP_KEY", "test-app-key")
    monkeypatch.setenv("KIS_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("KIS_TOKEN_SCOPE", "test-scope")
    monkeypatch.setenv("IDENTITY_DATABASE_URL", "postgresql+asyncpg://user:password@localhost/database")
    monkeypatch.setenv("AUTOMATION_DATABASE_URL", "postgresql+asyncpg://user:password@localhost/database")
    monkeypatch.setenv("ACCOUNT_SHARD_1_DATABASE_URL", "postgresql+asyncpg://user:password@localhost/database")
    monkeypatch.setenv("ACCOUNT_SHARD_2_DATABASE_URL", "postgresql+asyncpg://user:password@localhost/database")
    class ReadyDependency:
        async def health_check(self) -> None:
            return None

    class UnavailableDependency:
        async def health_check(self) -> None:
            raise OSError('database unavailable')

    with TestClient(app) as client:
        response = client.get("/health")
        app.state.session_registry = UnavailableDependency()
        not_ready = client.get("/readiness")
        app.state.session_registry = ReadyDependency()
        app.state.session_store = ReadyDependency()
        readiness = client.get("/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not_ready.status_code == 503
    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ready"}
