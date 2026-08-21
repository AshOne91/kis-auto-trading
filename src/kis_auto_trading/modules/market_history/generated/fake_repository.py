from uuid import UUID

from kis_auto_trading.modules.market_history.generated.models import DomesticDailyCandle


class FakeDomesticDailyCandleRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, DomesticDailyCandle] = {}

    async def find_by_id(
        self, candle_id: UUID,
    ) -> DomesticDailyCandle | None:
        return self._items.get(candle_id)

    async def save(
        self, aggregate: DomesticDailyCandle,
    ) -> None:
        self._items[aggregate.candle_id] = aggregate
