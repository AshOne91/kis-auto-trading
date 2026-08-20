from __future__ import annotations

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.infrastructure.outbox.repository import OutboxWriter
from kis_auto_trading.modules.signal.generated.models import SignalEvent
from kis_auto_trading.modules.signal.generated.sqlalchemy_repositories import (
    SQLAlchemySignalEventRepository,
)


async def record_signal(
    signal: SignalEvent,
    session_registry: AsyncSessionRegistry,
) -> SignalEvent:
    """Persist a signal and enqueue its domain event in one transaction."""
    async with session_registry.session(ShardTarget(store="automation")) as session:
        repository = SQLAlchemySignalEventRepository(session)
        existing = await repository.find_by_id(signal.signal_id)
        if existing is not None:
            return existing

        await repository.save(signal)
        OutboxWriter(session).add(
            EventMessage(
                event_type="signal.created",
                aggregate_id=str(signal.signal_id),
                routing_key="signal.created",
                payload=signal.model_dump(mode="json"),
            )
        )
    return signal
