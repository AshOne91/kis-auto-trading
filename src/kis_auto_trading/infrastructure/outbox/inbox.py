from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.infrastructure.outbox.models import (
    ProcessedMessageRecord,
)


class ProcessedMessageInbox:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, event_id: str) -> bool:
        statement = (
            insert(ProcessedMessageRecord)
            .values(event_id=event_id, processed_at=datetime.now(UTC))
            .on_conflict_do_nothing(index_elements=['event_id'])
        )
        result = await self._session.execute(statement)
        return result.rowcount == 1
