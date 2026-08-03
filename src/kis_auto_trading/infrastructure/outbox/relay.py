from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.infrastructure.messaging.protocol import (
    EventMessage,
    MessagePublisher,
    MessagePublishError,
)
from kis_auto_trading.infrastructure.outbox.models import OutboxEventRecord


class OutboxRelay:
    def __init__(self, publisher: MessagePublisher, batch_size: int = 100) -> None:
        self._publisher = publisher
        self._batch_size = batch_size

    async def publish_pending(self, session: AsyncSession) -> int:
        now = datetime.now(UTC)
        result = await session.execute(
            select(OutboxEventRecord)
            .where(
                OutboxEventRecord.status == 'pending',
                OutboxEventRecord.available_at <= now,
            )
            .order_by(OutboxEventRecord.occurred_at)
            .limit(self._batch_size)
            .with_for_update(skip_locked=True)
        )
        records = list(result.scalars())
        published = 0
        for record in records:
            record.attempts += 1
            try:
                await self._publisher.publish(
                    EventMessage(
                        event_id=record.event_id,
                        event_type=record.event_type,
                        event_version=record.event_version,
                        aggregate_id=record.aggregate_id,
                        payload=record.payload,
                        routing_key=record.routing_key,
                        occurred_at=record.occurred_at,
                    )
                )
            except MessagePublishError as error:
                record.last_error = str(error)[:2000]
                delay = min(60, 2 ** min(record.attempts, 6))
                record.available_at = now + timedelta(seconds=delay)
            else:
                record.status = 'published'
                record.published_at = datetime.now(UTC)
                record.last_error = None
                published += 1
        return published
