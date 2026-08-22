from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BrokerageAccountConnection(BaseModel):
    connection_id: UUID
    user_id: UUID
    provider: str
    environment: str
    display_name: str
    account_mask: str
    credential_ref: str
    status: str
    created_at: datetime
    updated_at: datetime
