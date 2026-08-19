import asyncio
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from kis_auto_trading.application.market_price_snapshots import (
    save_market_price_snapshot,
)
from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_market_data import KisDomesticStockPrice
from kis_auto_trading.modules.market_data.generated.sqlalchemy_repositories import (
    SQLAlchemyMarketPriceSnapshotRepository,
)

_DATABASE_URL_ENV = "KIS_MARKET_DATA_DATABASE_URL"


def test_market_price_snapshot_round_trips_through_automation_database() -> None:
    database_url = os.getenv(_DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(f"set {_DATABASE_URL_ENV} to enable database integration")

    async def scenario() -> None:
        engine = create_async_engine(database_url)
        registry = AsyncSessionRegistry({"automation": engine}, {})
        price = KisDomesticStockPrice(
            stock_code="005930",
            current_price="70000",
            output={"stck_prpr": "70000"},
        )
        try:
            snapshot = await save_market_price_snapshot(registry, price)
            async with registry.session(ShardTarget(store="automation")) as session:
                stored = await SQLAlchemyMarketPriceSnapshotRepository(
                    session
                ).find_by_id(snapshot.snapshot_id)
        finally:
            await engine.dispose()

        assert stored == snapshot
        assert stored.observed_at.tzinfo is not None
        assert stored.observed_at <= datetime.now(UTC)

    asyncio.run(scenario())
