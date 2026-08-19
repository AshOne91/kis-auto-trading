from datetime import UTC, datetime
from uuid import uuid4

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_market_data import KisDomesticStockPrice
from kis_auto_trading.modules.market_data.generated.models import MarketPriceSnapshot
from kis_auto_trading.modules.market_data.generated.sqlalchemy_repositories import (
    SQLAlchemyMarketPriceSnapshotRepository,
)


async def save_market_price_snapshot(
    session_registry: AsyncSessionRegistry,
    price: KisDomesticStockPrice,
) -> MarketPriceSnapshot:
    snapshot = MarketPriceSnapshot(
        snapshot_id=uuid4(),
        stock_code=price.stock_code,
        current_price=price.current_price,
        observed_at=datetime.now(UTC),
    )
    async with session_registry.session(ShardTarget(store="automation")) as session:
        await SQLAlchemyMarketPriceSnapshotRepository(session).save(snapshot)
    return snapshot
