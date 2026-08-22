import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.outbox.models import OutboxEventRecord
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.brokerage_account import handlers
from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)


class RecordingSessionRegistry:
    def __init__(self) -> None:
        self.targets: list[ShardTarget] = []
        self.recording_session = RecordingSession()

    @asynccontextmanager
    async def session(self, target: ShardTarget) -> AsyncIterator[object]:
        self.targets.append(target)
        yield self.recording_session


class MemoryConnectionRepository:
    connection: BrokerageAccountConnection | None = None

    def __init__(self, session: object) -> None:
        del session

    async def find_by_id(
        self, connection_id: UUID
    ) -> BrokerageAccountConnection | None:
        connection = type(self).connection
        if connection is None or connection.connection_id != connection_id:
            return None
        return connection

    async def save(self, aggregate: BrokerageAccountConnection) -> None:
        type(self).connection = aggregate


@pytest.fixture(autouse=True)
def use_memory_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    MemoryConnectionRepository.connection = None
    monkeypatch.setattr(
        handlers,
        "SQLAlchemyBrokerageAccountConnectionRepository",
        MemoryConnectionRepository,
    )


def _configure_account(monkeypatch: pytest.MonkeyPatch, user_id: UUID) -> None:
    monkeypatch.setenv("KIS_ACCOUNT_OWNER_USER_ID", str(user_id))
    monkeypatch.setenv("KIS_ACCOUNT_NUMBER", "12345678")
    monkeypatch.setenv("KIS_ACCOUNT_PRODUCT_CODE", "01")
    monkeypatch.setenv("KIS_ACCOUNT_ENVIRONMENT", "demo")


def _session(user_id: UUID, shard_id: str = "2") -> SessionData:
    return SessionData(
        session_id="session-id",
        user_id=str(user_id),
        data={"shard_id": shard_id, "access_level": "user"},
    )


@pytest.mark.anyio
async def test_link_and_get_default_connection_are_sharded_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    _configure_account(monkeypatch, user_id)
    registry = RecordingSessionRegistry()
    typed_registry = cast(AsyncSessionRegistry, registry)

    first = await handlers.link_default_connection(
        _session(user_id), typed_registry
    )
    second = await handlers.link_default_connection(
        _session(user_id), typed_registry
    )
    loaded = await handlers.get_connection(_session(user_id), typed_registry)

    assert first == second == loaded
    assert first.user_id == user_id
    assert first.provider == "kis"
    assert first.environment == "demo"
    assert first.account_mask == "****5678"
    assert first.credential_ref == "kis:default"
    assert first.created_at.tzinfo is not None
    assert registry.targets == [
        ShardTarget(store="account", shard_id="2"),
        ShardTarget(store="account", shard_id="2"),
        ShardTarget(store="account", shard_id="2"),
    ]
    assert len(registry.recording_session.added) == 1
    outbox = registry.recording_session.added[0]
    assert isinstance(outbox, OutboxEventRecord)
    assert outbox.event_type == "brokerage.account.connection-linked"
    assert outbox.payload == {
        "connection_id": str(first.connection_id),
        "user_id": str(user_id),
        "shard_id": "2",
        "provider": "kis",
        "status": "active",
    }
    serialized = first.model_dump_json() + json.dumps(outbox.payload)
    assert "12345678" not in serialized
    assert {
        "account_number",
        "account_product_code",
        "app_key",
        "app_secret",
    }.isdisjoint(first.model_dump())


@pytest.mark.anyio
async def test_link_rejects_a_user_other_than_the_deployment_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_user_id = uuid4()
    _configure_account(monkeypatch, owner_user_id)
    registry = RecordingSessionRegistry()

    with pytest.raises(HTTPException) as error:
        await handlers.link_default_connection(
            _session(uuid4()), cast(AsyncSessionRegistry, registry)
        )

    assert error.value.status_code == 403
    assert registry.targets == []


@pytest.mark.anyio
async def test_link_fails_closed_when_owner_or_credentials_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    registry = cast(AsyncSessionRegistry, RecordingSessionRegistry())

    monkeypatch.delenv("KIS_ACCOUNT_OWNER_USER_ID", raising=False)
    with pytest.raises(HTTPException) as missing_owner:
        await handlers.link_default_connection(_session(user_id), registry)
    assert missing_owner.value.status_code == 503

    _configure_account(monkeypatch, user_id)
    monkeypatch.delenv("KIS_ACCOUNT_NUMBER")
    with pytest.raises(HTTPException) as missing_credentials:
        await handlers.link_default_connection(_session(user_id), registry)
    assert missing_credentials.value.status_code == 503


@pytest.mark.anyio
async def test_get_connection_returns_not_found_for_unlinked_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    _configure_account(monkeypatch, user_id)

    with pytest.raises(HTTPException) as error:
        await handlers.get_connection(
            _session(user_id),
            cast(AsyncSessionRegistry, RecordingSessionRegistry()),
        )

    assert error.value.status_code == 404
