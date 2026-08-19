import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from kis_auto_trading.modules.market_data.generated.fake_repository import (
    FakeMarketPriceSnapshotRepository,
)
from kis_auto_trading.modules.market_data.generated.models import MarketPriceSnapshot


def test_market_price_snapshot_repository_round_trips_global_snapshot() -> None:
    async def scenario() -> None:
        repository = FakeMarketPriceSnapshotRepository()
        snapshot = MarketPriceSnapshot(
            snapshot_id=uuid4(),
            stock_code="005930",
            current_price="75000",
            observed_at=datetime.now(UTC),
        )

        await repository.save(snapshot)

        assert await repository.find_by_id(snapshot.snapshot_id) == snapshot

    asyncio.run(scenario())
