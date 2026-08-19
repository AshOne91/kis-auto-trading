from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from kis_auto_trading.infrastructure.database.base import Base


class MarketPriceSnapshotRecord(Base):
    __tablename__ = "market_price_snapshots"

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    stock_code: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    current_price: Mapped[str] = mapped_column(Text, nullable=False)

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
