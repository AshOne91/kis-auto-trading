import pytest
from fastapi.testclient import TestClient

from kis_auto_trading.main import app


def test_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_SENTINEL_URLS", "localhost:26379")
    monkeypatch.setenv("IDENTITY_DATABASE_URL", "postgresql+asyncpg://user:password@localhost/database")
    monkeypatch.setenv("ACCOUNT_SHARD_1_DATABASE_URL", "postgresql+asyncpg://user:password@localhost/database")
    monkeypatch.setenv("ACCOUNT_SHARD_2_DATABASE_URL", "postgresql+asyncpg://user:password@localhost/database")
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
