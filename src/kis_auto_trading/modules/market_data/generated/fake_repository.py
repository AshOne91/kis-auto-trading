from uuid import UUID

from kis_auto_trading.modules.market_data.generated.models import MarketPriceSnapshot


class FakeMarketPriceSnapshotRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, MarketPriceSnapshot] = {}

    async def find_by_id(
        self, snapshot_id: UUID,
    ) -> MarketPriceSnapshot | None:
        return self._items.get(snapshot_id)

    async def save(
        self, aggregate: MarketPriceSnapshot,
    ) -> None:
        self._items[aggregate.snapshot_id] = aggregate
