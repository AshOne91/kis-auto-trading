from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class InAppNotification(BaseModel):
    notification_id: UUID
    delivery_intent_id: UUID
    user_id: UUID
    signal_id: UUID
    stock_code: str
    created_at: datetime
    read_at: datetime | None = None
