from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.notification.generated.models import InAppNotification
from kis_auto_trading.modules.notification.generated.sqlalchemy_models import (
    InAppNotificationRecord,
)


class SQLAlchemyInAppNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, notification_id: UUID,
    ) -> InAppNotification | None:
        record = await self._session.get(
            InAppNotificationRecord, notification_id
        )
        if record is None:
            return None
        return InAppNotification(
            notification_id=record.notification_id,
            delivery_intent_id=record.delivery_intent_id,
            user_id=record.user_id,
            signal_id=record.signal_id,
            stock_code=record.stock_code,
            created_at=record.created_at,
            read_at=record.read_at
        )

    async def save(
        self, aggregate: InAppNotification,
    ) -> None:
        record = InAppNotificationRecord(
            notification_id=aggregate.notification_id,
            delivery_intent_id=aggregate.delivery_intent_id,
            user_id=aggregate.user_id,
            signal_id=aggregate.signal_id,
            stock_code=aggregate.stock_code,
            created_at=aggregate.created_at,
            read_at=aggregate.read_at
        )
        await self._session.merge(record)
