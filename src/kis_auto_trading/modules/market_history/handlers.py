from uuid import NAMESPACE_URL, uuid5

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_market_data import KisDomesticDailyCandle
from kis_auto_trading.modules.market_history.generated.models import DomesticDailyCandle
from kis_auto_trading.modules.market_history.generated.sqlalchemy_repositories import (
    SQLAlchemyDomesticDailyCandleRepository,
)


async def save_domestic_daily_candles(
    session_registry: AsyncSessionRegistry,
    candles: tuple[KisDomesticDailyCandle, ...],
) -> tuple[DomesticDailyCandle, ...]:
    models = tuple(
        DomesticDailyCandle(
            candle_id=uuid5(
                NAMESPACE_URL,
                f"kis:domestic-daily:{candle.stock_code}:{candle.trading_date}",
            ),
            stock_code=candle.stock_code,
            trading_date=candle.trading_date,
            open_price=candle.open_price,
            high_price=candle.high_price,
            low_price=candle.low_price,
            close_price=candle.close_price,
            volume=candle.volume,
        )
        for candle in candles
    )
    async with session_registry.session(ShardTarget(store="automation")) as session:
        repository = SQLAlchemyDomesticDailyCandleRepository(session)
        for model in models:
            await repository.save(model)
    return models


async def list_domestic_daily_candles(
    session_registry: AsyncSessionRegistry,
    stock_code: str,
) -> list[DomesticDailyCandle]:
    async with session_registry.session(ShardTarget(store="automation")) as session:
        return await SQLAlchemyDomesticDailyCandleRepository(
            session
        ).list_by_stock_code(stock_code)
