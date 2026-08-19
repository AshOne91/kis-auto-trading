from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.market_data.generated.models import MarketPriceSnapshot
from kis_auto_trading.modules.market_data.generated.sqlalchemy_models import (
    MarketPriceSnapshotRecord,
)


class SQLAlchemyMarketPriceSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, snapshot_id: UUID,
    ) -> MarketPriceSnapshot | None:
        record = await self._session.get(
            MarketPriceSnapshotRecord, snapshot_id
        )
        if record is None:
            return None
        return MarketPriceSnapshot(
            snapshot_id=record.snapshot_id,
            stock_code=record.stock_code,
            current_price=record.current_price,
            observed_at=record.observed_at
        )

    async def save(
        self, aggregate: MarketPriceSnapshot,
    ) -> None:
        record = MarketPriceSnapshotRecord(
            snapshot_id=aggregate.snapshot_id,
            stock_code=aggregate.stock_code,
            current_price=aggregate.current_price,
            observed_at=aggregate.observed_at
        )
        await self._session.merge(record)
