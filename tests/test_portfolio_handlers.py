from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisDomesticAccountClient,
    KisDomesticStockHolding,
)
from kis_auto_trading.infrastructure.outbox.models import OutboxEventRecord
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)
from kis_auto_trading.modules.portfolio import handlers
from kis_auto_trading.modules.portfolio.generated.models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)


class TransactionSession:
    def __init__(self, registry: MemorySessionRegistry) -> None:
        self.snapshots = dict(registry.snapshots)
        self.positions = dict(registry.positions)
        self.events = list(registry.events)

    def add(self, value: object) -> None:
        self.events.append(value)


class MemorySessionRegistry:
    def __init__(self) -> None:
        self.snapshots: dict[UUID, PortfolioSnapshot] = {}
        self.positions: dict[UUID, PortfolioPositionSnapshot] = {}
        self.events: list[object] = []
        self.targets: list[ShardTarget] = []
        self.rollbacks = 0

    @asynccontextmanager
    async def session(self, target: ShardTarget) -> AsyncIterator[TransactionSession]:
        self.targets.append(target)
        session = TransactionSession(self)
        try:
            yield session
        except Exception:
            self.rollbacks += 1
            raise
        else:
            self.snapshots = session.snapshots
            self.positions = session.positions
            self.events = session.events


class MemorySnapshotRepository:
    def __init__(self, session: TransactionSession) -> None:
        self._session = session

    async def find_by_id(self, snapshot_id: UUID) -> PortfolioSnapshot | None:
        return self._session.snapshots.get(snapshot_id)

    async def save(self, aggregate: PortfolioSnapshot) -> None:
        self._session.snapshots[aggregate.snapshot_id] = aggregate


class MemoryPositionRepository:
    fail_on_save = False

    def __init__(self, session: TransactionSession) -> None:
        self._session = session

    async def find_by_id(
        self, position_id: UUID
    ) -> PortfolioPositionSnapshot | None:
        return self._session.positions.get(position_id)

    async def save(self, aggregate: PortfolioPositionSnapshot) -> None:
        if type(self).fail_on_save:
            raise RuntimeError("position write failed")
        self._session.positions[aggregate.position_id] = aggregate

    async def list_by_snapshot_id(
        self, snapshot_id: UUID
    ) -> list[PortfolioPositionSnapshot]:
        return sorted(
            (
                position
                for position in self._session.positions.values()
                if position.snapshot_id == snapshot_id
            ),
            key=lambda position: position.stock_code,
        )


@dataclass
class FakeAccountClient:
    holdings: tuple[KisDomesticStockHolding, ...] = ()
    requests: int = 0

    async def list_domestic_stock_holdings(self) -> tuple[KisDomesticStockHolding, ...]:
        self.requests += 1
        return self.holdings


@pytest.fixture(autouse=True)
def use_memory_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    MemoryPositionRepository.fail_on_save = False
    monkeypatch.setattr(
        handlers,
        "SQLAlchemyPortfolioSnapshotRepository",
        MemorySnapshotRepository,
    )
    monkeypatch.setattr(
        handlers,
        "SQLAlchemyPortfolioPositionSnapshotRepository",
        MemoryPositionRepository,
    )


def _session(user_id: UUID, shard_id: str = "2") -> SessionData:
    return SessionData(
        session_id="session-id",
        user_id=str(user_id),
        data={"shard_id": shard_id, "access_level": "user"},
    )


def _connection(user_id: UUID) -> BrokerageAccountConnection:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    return BrokerageAccountConnection(
        connection_id=uuid4(),
        user_id=user_id,
        provider="kis",
        environment="demo",
        display_name="KIS default account",
        account_mask="****5678",
        credential_ref="kis:default",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _holding(stock_code: str) -> KisDomesticStockHolding:
    return KisDomesticStockHolding(
        stock_code=stock_code,
        product_name=f"Stock {stock_code}",
        holding_quantity="10",
        orderable_quantity="8",
        current_price="70000",
    )


@pytest.mark.anyio
async def test_capture_is_sharded_atomic_and_idempotent() -> None:
    user_id = uuid4()
    connection = _connection(user_id)
    registry = MemorySessionRegistry()
    account = FakeAccountClient(holdings=(_holding("035420"), _holding("005930")))

    first = await handlers.capture_portfolio_snapshot(
        _session(user_id),
        cast(AsyncSessionRegistry, registry),
        connection,
        cast(KisDomesticAccountClient, account),
        "daily-close",
    )
    replayed = await handlers.capture_portfolio_snapshot(
        _session(user_id),
        cast(AsyncSessionRegistry, registry),
        connection,
        cast(KisDomesticAccountClient, account),
        "daily-close",
    )
    loaded = await handlers.get_portfolio_snapshot(
        _session(user_id),
        cast(AsyncSessionRegistry, registry),
        first.snapshot.snapshot_id,
    )

    assert replayed == loaded == first
    assert first.snapshot.user_id == user_id
    assert first.snapshot.connection_id == connection.connection_id
    assert first.snapshot.position_count == 2
    assert [position.stock_code for position in first.positions] == ["005930", "035420"]
    assert account.requests == 1
    assert registry.targets == [
        ShardTarget(store="account", shard_id="2"),
        ShardTarget(store="account", shard_id="2"),
        ShardTarget(store="account", shard_id="2"),
        ShardTarget(store="account", shard_id="2"),
    ]
    assert len(registry.events) == 1
    event = registry.events[0]
    assert isinstance(event, OutboxEventRecord)
    assert event.event_type == "portfolio.snapshot.captured"
    assert event.payload == {
        "snapshot_id": str(first.snapshot.snapshot_id),
        "connection_id": str(connection.connection_id),
        "user_id": str(user_id),
        "shard_id": "2",
        "position_count": 2,
    }


@pytest.mark.anyio
async def test_capture_persists_an_empty_snapshot() -> None:
    user_id = uuid4()
    registry = MemorySessionRegistry()
    account = FakeAccountClient()

    capture = await handlers.capture_portfolio_snapshot(
        _session(user_id),
        cast(AsyncSessionRegistry, registry),
        _connection(user_id),
        cast(KisDomesticAccountClient, account),
        "empty",
    )

    assert capture.snapshot.position_count == 0
    assert capture.positions == ()
    assert registry.positions == {}
    assert len(registry.events) == 1


@pytest.mark.anyio
async def test_capture_rejects_foreign_ownership_before_io() -> None:
    user_id = uuid4()
    registry = MemorySessionRegistry()
    account = FakeAccountClient()

    with pytest.raises(HTTPException) as error:
        await handlers.capture_portfolio_snapshot(
            _session(user_id),
            cast(AsyncSessionRegistry, registry),
            _connection(uuid4()),
            cast(KisDomesticAccountClient, account),
            "foreign",
        )

    assert error.value.status_code == 403
    assert account.requests == 0
    assert registry.targets == []


@pytest.mark.anyio
async def test_capture_rolls_back_the_snapshot_and_outbox_on_position_failure() -> None:
    user_id = uuid4()
    registry = MemorySessionRegistry()
    account = FakeAccountClient(holdings=(_holding("005930"),))
    MemoryPositionRepository.fail_on_save = True

    with pytest.raises(RuntimeError, match="position write failed"):
        await handlers.capture_portfolio_snapshot(
            _session(user_id),
            cast(AsyncSessionRegistry, registry),
            _connection(user_id),
            cast(KisDomesticAccountClient, account),
            "rollback",
        )

    assert registry.rollbacks == 1
    assert registry.snapshots == {}
    assert registry.positions == {}
    assert registry.events == []


@pytest.mark.anyio
async def test_get_snapshot_hides_missing_and_foreign_ownership() -> None:
    user_id = uuid4()
    registry = MemorySessionRegistry()

    with pytest.raises(HTTPException) as missing:
        await handlers.get_portfolio_snapshot(
            _session(user_id),
            cast(AsyncSessionRegistry, registry),
            uuid4(),
        )

    foreign_id = uuid4()
    registry.snapshots[foreign_id] = PortfolioSnapshot(
        snapshot_id=foreign_id,
        connection_id=uuid4(),
        user_id=uuid4(),
        captured_at=datetime(2026, 8, 22, tzinfo=UTC),
        position_count=0,
    )
    with pytest.raises(HTTPException) as foreign:
        await handlers.get_portfolio_snapshot(
            _session(user_id),
            cast(AsyncSessionRegistry, registry),
            foreign_id,
        )

    assert missing.value.status_code == 404
    assert foreign.value.status_code == 404
    assert registry.targets == [
        ShardTarget(store="account", shard_id="2"),
        ShardTarget(store="account", shard_id="2"),
    ]
