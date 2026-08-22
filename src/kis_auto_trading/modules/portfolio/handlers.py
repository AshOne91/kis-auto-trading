from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException, status

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisDomesticAccountClient,
    KisDomesticStockHolding,
)
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.infrastructure.outbox.repository import OutboxWriter
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)
from kis_auto_trading.modules.portfolio.generated.models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)
from kis_auto_trading.modules.portfolio.generated.sqlalchemy_repositories import (
    SQLAlchemyPortfolioPositionSnapshotRepository,
    SQLAlchemyPortfolioSnapshotRepository,
)


@dataclass(frozen=True, slots=True)
class PortfolioSnapshotCapture:
    snapshot: PortfolioSnapshot
    positions: tuple[PortfolioPositionSnapshot, ...]


async def capture_portfolio_snapshot(
    current_session: SessionData,
    session_registry: AsyncSessionRegistry,
    connection: BrokerageAccountConnection,
    account: KisDomesticAccountClient,
    idempotency_key: str,
) -> PortfolioSnapshotCapture:
    user_id, target = _snapshot_location(current_session, connection)
    snapshot_id = _snapshot_id(user_id, connection.connection_id, idempotency_key)

    existing = await _find_capture(session_registry, target, snapshot_id)
    if existing is not None:
        return existing

    holdings = await account.list_domestic_stock_holdings()
    captured_at = datetime.now(UTC)
    positions = _position_models(snapshot_id, user_id, holdings)
    snapshot = PortfolioSnapshot(
        snapshot_id=snapshot_id,
        connection_id=connection.connection_id,
        user_id=user_id,
        captured_at=captured_at,
        position_count=len(positions),
    )

    async with session_registry.session(target) as session:
        snapshot_repository = SQLAlchemyPortfolioSnapshotRepository(session)
        existing_snapshot = await snapshot_repository.find_by_id(snapshot_id)
        if existing_snapshot is not None:
            existing_positions = await SQLAlchemyPortfolioPositionSnapshotRepository(
                session
            ).list_by_snapshot_id(snapshot_id)
            return PortfolioSnapshotCapture(
                snapshot=existing_snapshot,
                positions=tuple(existing_positions),
            )

        await snapshot_repository.save(snapshot)
        position_repository = SQLAlchemyPortfolioPositionSnapshotRepository(session)
        for position in positions:
            await position_repository.save(position)
        OutboxWriter(session).add(
            EventMessage(
                event_type="portfolio.snapshot.captured",
                aggregate_id=str(snapshot_id),
                routing_key="portfolio.snapshot.captured",
                payload={
                    "snapshot_id": str(snapshot_id),
                    "connection_id": str(connection.connection_id),
                    "user_id": str(user_id),
                    "shard_id": target.shard_id or "",
                    "position_count": len(positions),
                },
            )
        )
    return PortfolioSnapshotCapture(snapshot=snapshot, positions=positions)


async def _find_capture(
    session_registry: AsyncSessionRegistry,
    target: ShardTarget,
    snapshot_id: UUID,
) -> PortfolioSnapshotCapture | None:
    async with session_registry.session(target) as session:
        snapshot = await SQLAlchemyPortfolioSnapshotRepository(session).find_by_id(
            snapshot_id
        )
        if snapshot is None:
            return None
        positions = await SQLAlchemyPortfolioPositionSnapshotRepository(
            session
        ).list_by_snapshot_id(snapshot_id)
    return PortfolioSnapshotCapture(snapshot=snapshot, positions=tuple(positions))


def _snapshot_location(
    current_session: SessionData,
    connection: BrokerageAccountConnection,
) -> tuple[UUID, ShardTarget]:
    try:
        user_id = UUID(current_session.user_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session user is invalid",
        ) from error
    if connection.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Brokerage account is not owned by this user",
        )
    shard_id = current_session.data.get("shard_id")
    if not isinstance(shard_id, str) or not shard_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session shard is missing",
        )
    return user_id, ShardTarget(store="account", shard_id=shard_id)


def _snapshot_id(user_id: UUID, connection_id: UUID, idempotency_key: str) -> UUID:
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must not be blank",
        )
    return uuid5(
        NAMESPACE_URL,
        f"autoforge:{user_id}:{connection_id}:portfolio-snapshot:{normalized_key}",
    )


def _position_models(
    snapshot_id: UUID,
    user_id: UUID,
    holdings: tuple[KisDomesticStockHolding, ...],
) -> tuple[PortfolioPositionSnapshot, ...]:
    by_stock_code = {holding.stock_code: holding for holding in holdings}
    return tuple(
        PortfolioPositionSnapshot(
            position_id=uuid5(snapshot_id, holding.stock_code),
            snapshot_id=snapshot_id,
            user_id=user_id,
            stock_code=holding.stock_code,
            product_name=holding.product_name,
            holding_quantity=holding.holding_quantity,
            orderable_quantity=holding.orderable_quantity,
            current_price=holding.current_price,
        )
        for holding in sorted(by_stock_code.values(), key=lambda item: item.stock_code)
    )
