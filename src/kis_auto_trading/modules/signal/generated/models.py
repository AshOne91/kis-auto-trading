from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SignalEvent(BaseModel):
    signal_id: UUID
    stock_code: str
    direction: str
    price: str
    confidence: float
    observed_at: datetime


class SignalSubscription(BaseModel):
    subscription_id: UUID
    user_id: UUID
    stock_code: str
    enabled: bool = True
