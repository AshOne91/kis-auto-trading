from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from kis_auto_trading.infrastructure.database.base import Base


class InAppNotificationRecord(Base):
    __tablename__ = "in_app_notifications"

    notification_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    delivery_intent_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    signal_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    stock_code: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
