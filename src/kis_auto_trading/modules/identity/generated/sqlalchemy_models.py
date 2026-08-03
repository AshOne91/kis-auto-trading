from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from kis_auto_trading.infrastructure.database.base import Base


class LoginAccountRecord(Base):
    __tablename__ = "login_accounts"

    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('TRUE'))

    shard_id: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
