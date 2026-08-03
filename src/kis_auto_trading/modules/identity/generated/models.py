from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class LoginAccount(BaseModel):
    user_id: UUID
    email: str
    password_hash: str
    is_active: bool = True
    shard_id: str
    created_at: datetime
