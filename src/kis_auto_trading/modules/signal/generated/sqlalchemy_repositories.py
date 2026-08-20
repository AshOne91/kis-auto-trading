from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.signal.generated.models import (
    SignalEvent,
    SignalSubscription,
)
from kis_auto_trading.modules.signal.generated.sqlalchemy_models import (
    SignalEventRecord,
    SignalSubscriptionRecord,
)


class SQLAlchemySignalEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, signal_id: UUID,
    ) -> SignalEvent | None:
        record = await self._session.get(
            SignalEventRecord, signal_id
        )
        if record is None:
            return None
        return SignalEvent(
            signal_id=record.signal_id,
            stock_code=record.stock_code,
            direction=record.direction,
            price=record.price,
            confidence=record.confidence,
            observed_at=record.observed_at
        )

    async def save(
        self, aggregate: SignalEvent,
    ) -> None:
        record = SignalEventRecord(
            signal_id=aggregate.signal_id,
            stock_code=aggregate.stock_code,
            direction=aggregate.direction,
            price=aggregate.price,
            confidence=aggregate.confidence,
            observed_at=aggregate.observed_at
        )
        await self._session.merge(record)


class SQLAlchemySignalSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, subscription_id: UUID,
    ) -> SignalSubscription | None:
        record = await self._session.get(
            SignalSubscriptionRecord, subscription_id
        )
        if record is None:
            return None
        return SignalSubscription(
            subscription_id=record.subscription_id,
            user_id=record.user_id,
            stock_code=record.stock_code,
            enabled=record.enabled
        )

    async def save(
        self, aggregate: SignalSubscription,
    ) -> None:
        record = SignalSubscriptionRecord(
            subscription_id=aggregate.subscription_id,
            user_id=aggregate.user_id,
            stock_code=aggregate.stock_code,
            enabled=aggregate.enabled
        )
        await self._session.merge(record)
