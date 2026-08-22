from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kis_auto_trading.infrastructure.database.provider import get_session_registry
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import (
    ReplayClaim,
    ReplayRecord,
    RequestReplayStore,
    SessionData,
)
from kis_auto_trading.infrastructure.session_store.provider import (
    get_current_session,
    get_request_replay_store,
)
from kis_auto_trading.modules.brokerage_account.generated import router as router_module
from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)


class MemoryReplayStore:
    def __init__(self) -> None:
        self.records: dict[str, ReplayRecord] = {}

    async def claim(
        self, key: str, fingerprint: str, ttl_seconds: int
    ) -> ReplayClaim | ReplayRecord:
        if key in self.records:
            return self.records[key]
        return ReplayClaim(
            key=key,
            fingerprint=fingerprint,
            token="claim-token",
            ttl_seconds=ttl_seconds,
        )

    async def complete(
        self, claim: ReplayClaim, status_code: int, body: str
    ) -> None:
        self.records[claim.key] = ReplayRecord(status_code=status_code, body=body)

    async def abort(self, claim: ReplayClaim) -> None:
        self.records.pop(claim.key, None)


def _session(access_level: str = "user") -> SessionData:
    return SessionData(
        session_id="session-id",
        user_id="00000000-0000-0000-0000-000000000001",
        data={"shard_id": "1", "access_level": access_level},
    )


def _connection() -> BrokerageAccountConnection:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    return BrokerageAccountConnection(
        connection_id=UUID("00000000-0000-0000-0000-000000000002"),
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        provider="kis",
        environment="demo",
        display_name="KIS default account",
        account_mask="****5678",
        credential_ref="kis:default",
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_brokerage_connection_routes_require_user_and_replay_link(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(router_module.router)
    replay_store = MemoryReplayStore()
    app.dependency_overrides[get_current_session] = _session
    app.dependency_overrides[get_session_registry] = lambda: cast(
        AsyncSessionRegistry, object()
    )
    app.dependency_overrides[get_request_replay_store] = lambda: cast(
        RequestReplayStore, replay_store
    )
    calls = 0

    async def fake_link(*_args) -> BrokerageAccountConnection:
        nonlocal calls
        calls += 1
        return _connection()

    async def fake_get(*_args) -> BrokerageAccountConnection:
        return _connection()

    monkeypatch.setattr(router_module.handlers, "link_default_connection", fake_link)
    monkeypatch.setattr(router_module.handlers, "get_connection", fake_get)

    with TestClient(app) as client:
        assert client.put("/api/brokerage-account/connection").status_code == 400
        first = client.put(
            "/api/brokerage-account/connection",
            headers={"Idempotency-Key": "link-default"},
        )
        replayed = client.put(
            "/api/brokerage-account/connection",
            headers={"Idempotency-Key": "link-default"},
        )
        loaded = client.get("/api/brokerage-account/connection")

    assert first.status_code == 200
    assert replayed.status_code == 200
    assert loaded.status_code == 200
    assert first.json() == replayed.json() == loaded.json()
    assert calls == 1

    app.dependency_overrides[get_current_session] = lambda: _session("anonymous")
    with TestClient(app) as client:
        denied = client.get("/api/brokerage-account/connection")
    assert denied.status_code == 403
