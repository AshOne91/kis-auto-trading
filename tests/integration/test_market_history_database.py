import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_market_data import KisDomesticDailyCandle
from kis_auto_trading.modules.market_history.generated.sqlalchemy_repositories import (
    SQLAlchemyDomesticDailyCandleRepository,
)
from kis_auto_trading.modules.market_history.handlers import save_domestic_daily_candles

_DATABASE_URL_ENV = "KIS_TEST_AUTOMATION_DATABASE_URL"


def test_domestic_daily_candle_round_trips_through_automation_database() -> None:
    database_url = os.getenv(_DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(f"set {_DATABASE_URL_ENV} to enable database integration")

    async def scenario() -> None:
        engine = create_async_engine(database_url)
        registry = AsyncSessionRegistry({"automation": engine}, {})
        source = (
            KisDomesticDailyCandle(
                stock_code="005930",
                trading_date="20260820",
                open_price="69000",
                high_price="70000",
                low_price="68000",
                close_price="69500",
                volume=100000,
            ),
            KisDomesticDailyCandle(
                stock_code="005930",
                trading_date="20260821",
                open_price="70000",
                high_price="71000",
                low_price="69000",
                close_price="70500",
                volume=123456,
            ),
        )
        try:
            saved = await save_domestic_daily_candles(registry, source)
            async with registry.session(ShardTarget(store="automation")) as session:
                stored = await SQLAlchemyDomesticDailyCandleRepository(
                    session
                ).list_by_stock_code("005930")
        finally:
            await engine.dispose()

        assert stored == [saved[1], saved[0]]

    asyncio.run(scenario())
