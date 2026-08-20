from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from uuid import uuid4

import pytest

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.outbox.models import OutboxEventRecord
from kis_auto_trading.modules.signal import handlers
from kis_auto_trading.modules.signal.generated.models import SignalEvent


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
    signals: dict[object, SignalEvent] = {}

    def __init__(self, session: object) -> None:
        del session

    async def find_by_id(self, signal_id: object) -> SignalEvent | None:
        return type(self).signals.get(signal_id)

    async def save(self, aggregate: SignalEvent) -> None:
        type(self).signals[aggregate.signal_id] = aggregate


@pytest.fixture(autouse=True)
def use_memory_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    MemorySignalRepository.signals = {}
    monkeypatch.setattr(
        handlers,
        "SQLAlchemySignalEventRepository",
        MemorySignalRepository,
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
async def test_record_signal_persists_and_enqueues_outbox_event() -> None:
    signal = _signal()
    registry = RecordingSessionRegistry()

    recorded = await handlers.record_signal(
        signal, cast(AsyncSessionRegistry, registry)
    )

    assert recorded == signal
    assert registry.targets == [ShardTarget(store="automation")]
    assert len(registry.recording_session.added) == 1
    outbox = registry.recording_session.added[0]
    assert isinstance(outbox, OutboxEventRecord)
    assert outbox.event_type == "signal.created"
    assert outbox.routing_key == "signal.created"
    assert outbox.aggregate_id == str(signal.signal_id)
    assert outbox.payload["stock_code"] == "005930"
    assert outbox.status == "pending"


@pytest.mark.anyio
async def test_record_signal_is_idempotent_for_existing_signal() -> None:
    signal = _signal()
    registry = RecordingSessionRegistry()

    first = await handlers.record_signal(signal, cast(AsyncSessionRegistry, registry))
    second = await handlers.record_signal(signal, cast(AsyncSessionRegistry, registry))

    assert first == second
    assert len(registry.recording_session.added) == 1
