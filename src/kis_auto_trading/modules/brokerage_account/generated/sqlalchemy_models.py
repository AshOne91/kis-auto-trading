from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from kis_auto_trading.infrastructure.database.base import Base


class BrokerageAccountConnectionRecord(Base):
    __tablename__ = "brokerage_account_connections"

    connection_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    provider: Mapped[str] = mapped_column(Text, nullable=False)

    environment: Mapped[str] = mapped_column(Text, nullable=False)

    display_name: Mapped[str] = mapped_column(Text, nullable=False)

    account_mask: Mapped[str] = mapped_column(Text, nullable=False)

    credential_ref: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
