from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.market_history.generated.models import DomesticDailyCandle
from kis_auto_trading.modules.market_history.generated.sqlalchemy_models import (
    DomesticDailyCandleRecord,
)


class SQLAlchemyDomesticDailyCandleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, candle_id: UUID,
    ) -> DomesticDailyCandle | None:
        record = await self._session.get(
            DomesticDailyCandleRecord, candle_id
        )
        if record is None:
            return None
        return DomesticDailyCandle(
            candle_id=record.candle_id,
            stock_code=record.stock_code,
            trading_date=record.trading_date,
            open_price=record.open_price,
            high_price=record.high_price,
            low_price=record.low_price,
            close_price=record.close_price,
            volume=record.volume
        )

    async def save(
        self, aggregate: DomesticDailyCandle,
    ) -> None:
        record = DomesticDailyCandleRecord(
            candle_id=aggregate.candle_id,
            stock_code=aggregate.stock_code,
            trading_date=aggregate.trading_date,
            open_price=aggregate.open_price,
            high_price=aggregate.high_price,
            low_price=aggregate.low_price,
            close_price=aggregate.close_price,
            volume=aggregate.volume
        )
        await self._session.merge(record)

    async def list_by_stock_code(
        self, stock_code: str,
    ) -> list[DomesticDailyCandle]:
        result = await self._session.execute(
            select(DomesticDailyCandleRecord).where(
                DomesticDailyCandleRecord.stock_code == stock_code
            ).order_by(
                DomesticDailyCandleRecord.trading_date.desc()
            ).limit(100)
        )
        records = result.scalars().all()
        return [
            DomesticDailyCandle(
            candle_id=record.candle_id,
            stock_code=record.stock_code,
            trading_date=record.trading_date,
            open_price=record.open_price,
            high_price=record.high_price,
            low_price=record.low_price,
            close_price=record.close_price,
            volume=record.volume
            )
            for record in records
        ]
