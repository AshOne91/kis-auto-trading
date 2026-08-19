from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MarketPriceSnapshot(BaseModel):
    snapshot_id: UUID
    stock_code: str
    current_price: str
    observed_at: datetime
