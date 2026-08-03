from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.infrastructure.outbox.models import OutboxEventRecord


class OutboxWriter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, message: EventMessage) -> None:
        occurred_at = message.occurred_at or datetime.now(UTC)
        self._session.add(
            OutboxEventRecord(
                event_id=message.event_id,
                event_type=message.event_type,
                event_version=message.event_version,
                aggregate_id=message.aggregate_id,
                routing_key=message.routing_key,
                payload=message.payload,
                status='pending',
                attempts=0,
                available_at=occurred_at,
                occurred_at=occurred_at,
            )
        )
