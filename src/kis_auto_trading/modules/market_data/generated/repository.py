from typing import Protocol
from uuid import UUID

from kis_auto_trading.modules.market_data.generated.models import MarketPriceSnapshot


class MarketPriceSnapshotRepository(Protocol):
    async def find_by_id(
        self, snapshot_id: UUID,
    ) -> MarketPriceSnapshot | None: ...
    async def save(
        self, aggregate: MarketPriceSnapshot,
    ) -> None: ...
