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
    expires_at: datetime | None = None


class SignalDeliveryIntent(BaseModel):
    intent_id: UUID
    signal_id: UUID
    subscription_id: UUID
    user_id: UUID
    shard_id: str
    stock_code: str
    expires_at: datetime
    status: str = 'pending'


class SignalSubscription(BaseModel):
    subscription_id: UUID
    user_id: UUID
    stock_code: str
    enabled: bool = True
    revision: int = 1


class SignalSubscriptionProjection(BaseModel):
    subscription_id: UUID
    user_id: UUID
    shard_id: str
    stock_code: str
    enabled: bool
    revision: int
