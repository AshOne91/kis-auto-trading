from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import ClassVar, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.outbox.models import OutboxEventRecord
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.signal import handlers
from kis_auto_trading.modules.signal.generated.models import (
    SignalEvent,
    SignalSubscription,
)
from kis_auto_trading.modules.signal.generated.schemas import (
    SubscribeRequest,
    UnsubscribeRequest,
)
from kis_auto_trading.modules.signal.subscription_policy import subscription_id


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


class MemorySignalRepository:
    signals: ClassVar[dict[object, SignalEvent]] = {}

    def __init__(self, session: object) -> None:
        del session

    async def find_by_id(self, signal_id: object) -> SignalEvent | None:
        return type(self).signals.get(signal_id)

    async def save(self, aggregate: SignalEvent) -> None:
        type(self).signals[aggregate.signal_id] = aggregate


class MemorySignalSubscriptionRepository:
    subscriptions: ClassVar[dict[object, SignalSubscription]] = {}

    def __init__(self, session: object) -> None:
        del session

    async def find_by_id(self, subscription_id: object) -> SignalSubscription | None:
        return type(self).subscriptions.get(subscription_id)

    async def save(self, aggregate: SignalSubscription) -> None:
        type(self).subscriptions[aggregate.subscription_id] = aggregate


@pytest.fixture(autouse=True)
def use_memory_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    MemorySignalRepository.signals = {}
    MemorySignalSubscriptionRepository.subscriptions = {}
    monkeypatch.setattr(
        handlers,
        "SQLAlchemySignalEventRepository",
        MemorySignalRepository,
    )
    monkeypatch.setattr(
        handlers,
        "SQLAlchemySignalSubscriptionRepository",
        MemorySignalSubscriptionRepository,
    )


def _signal() -> SignalEvent:
    return SignalEvent(
        signal_id=uuid4(),
        stock_code="005930",
        direction="BUY",
        price="70000",
        confidence=0.91,
        observed_at="2026-08-20T00:00:00Z",
    )


@pytest.mark.anyio
async def test_record_signal_persists_without_unroutable_outbox_event() -> None:
    signal = _signal()
    registry = RecordingSessionRegistry()

    recorded = await handlers.record_signal(
        signal, cast(AsyncSessionRegistry, registry)
    )

    assert recorded == signal
    assert registry.targets == [ShardTarget(store="automation")]
    assert registry.recording_session.added == []


@pytest.mark.anyio
async def test_record_signal_is_idempotent_for_existing_signal() -> None:
    signal = _signal()
    registry = RecordingSessionRegistry()

    first = await handlers.record_signal(signal, cast(AsyncSessionRegistry, registry))
    second = await handlers.record_signal(signal, cast(AsyncSessionRegistry, registry))

    assert first == second
    assert registry.recording_session.added == []


@pytest.mark.anyio
async def test_record_signal_with_expiry_enqueues_delivery_materialization() -> None:
    signal = SignalEvent(
        signal_id=uuid4(),
        stock_code="005930",
        direction="BUY",
        price="70000",
        confidence=0.91,
        observed_at="2026-08-20T00:00:00Z",
        expires_at="2099-08-20T00:05:00Z",
    )
    registry = RecordingSessionRegistry()

    await handlers.record_signal(signal, cast(AsyncSessionRegistry, registry))

    assert len(registry.recording_session.added) == 1
    event = registry.recording_session.added[0]
    assert isinstance(event, OutboxEventRecord)
    assert event.event_type == "signal.created"
    assert event.routing_key == "signal.created"
    assert event.payload["signal_id"] == str(signal.signal_id)


@pytest.mark.anyio
async def test_subscription_state_changes_are_sharded_and_enqueued() -> None:
    user_id = uuid4()
    current_session = SessionData(
        session_id="session-id",
        user_id=str(user_id),
        data={"shard_id": "2"},
    )
    registry = RecordingSessionRegistry()
    typed_registry = cast(AsyncSessionRegistry, registry)

    subscribed = await handlers.subscribe(
        SubscribeRequest(stock_code="005930"), current_session, typed_registry
    )
    repeated = await handlers.subscribe(
        SubscribeRequest(stock_code="005930"), current_session, typed_registry
    )
    unsubscribed = await handlers.unsubscribe(
        UnsubscribeRequest(stock_code="005930"), current_session, typed_registry
    )
    repeated_unsubscribe = await handlers.unsubscribe(
        UnsubscribeRequest(stock_code="005930"), current_session, typed_registry
    )

    assert subscribed.subscription_id == subscription_id(user_id, "005930")
    assert subscribed.enabled is True
    assert subscribed.revision == 1
    assert repeated == subscribed
    assert unsubscribed.enabled is False
    assert unsubscribed.revision == 2
    assert repeated_unsubscribe == unsubscribed
    assert registry.targets == [ShardTarget(store="account", shard_id="2")] * 4
    assert len(registry.recording_session.added) == 2
    assert all(
        isinstance(record, OutboxEventRecord)
        and record.event_type == "signal.subscription.updated"
        for record in registry.recording_session.added
    )
    assert registry.recording_session.added[0].payload["enabled"] is True
    assert registry.recording_session.added[0].payload["revision"] == 1
    assert registry.recording_session.added[1].payload["enabled"] is False
    assert registry.recording_session.added[1].payload["revision"] == 2


@pytest.mark.anyio
async def test_subscription_rejects_non_domestic_stock_code() -> None:
    current_session = SessionData(
        session_id="session-id",
        user_id=str(uuid4()),
        data={"shard_id": "2"},
    )
    registry = cast(AsyncSessionRegistry, RecordingSessionRegistry())

    with pytest.raises(HTTPException) as error:
        await handlers.subscribe(
            SubscribeRequest(stock_code="AAPL"), current_session, registry
        )

    assert error.value.status_code == 422
