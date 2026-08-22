from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PortfolioSnapshot(BaseModel):
    snapshot_id: UUID
    connection_id: UUID
    user_id: UUID
    captured_at: datetime
    position_count: int


class PortfolioPositionSnapshot(BaseModel):
    position_id: UUID
    snapshot_id: UUID
    user_id: UUID
    stock_code: str
    product_name: str
    holding_quantity: str
    orderable_quantity: str
    current_price: str
