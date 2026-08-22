from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from kis_auto_trading.infrastructure.database.base import Base


class PortfolioSnapshotRecord(Base):
    __tablename__ = "portfolio_snapshots"

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    connection_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    position_count: Mapped[int] = mapped_column(BigInteger, nullable=False)


class PortfolioPositionSnapshotRecord(Base):
    __tablename__ = "portfolio_position_snapshots"

    position_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    stock_code: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    product_name: Mapped[str] = mapped_column(Text, nullable=False)

    holding_quantity: Mapped[str] = mapped_column(Text, nullable=False)

    orderable_quantity: Mapped[str] = mapped_column(Text, nullable=False)

    current_price: Mapped[str] = mapped_column(Text, nullable=False)
