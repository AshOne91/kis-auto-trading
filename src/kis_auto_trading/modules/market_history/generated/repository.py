from typing import Protocol
from uuid import UUID

from kis_auto_trading.modules.market_history.generated.models import DomesticDailyCandle


class DomesticDailyCandleRepository(Protocol):
    async def find_by_id(
        self, candle_id: UUID,
    ) -> DomesticDailyCandle | None: ...
    async def save(
        self, aggregate: DomesticDailyCandle,
    ) -> None: ...
    async def list_by_stock_code(
        self, stock_code: str,
    ) -> list[DomesticDailyCandle]: ...
