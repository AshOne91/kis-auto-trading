from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class DomesticDailyCandle(BaseModel):
    candle_id: UUID
    stock_code: str
    trading_date: str
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    volume: int
