from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from kis_auto_trading.infrastructure.database.base import Base


class SignalEventRecord(Base):
    __tablename__ = "signal_events"

    signal_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    stock_code: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    direction: Mapped[str] = mapped_column(Text, nullable=False)

    price: Mapped[str] = mapped_column(Text, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class SignalSubscriptionRecord(Base):
    __tablename__ = "signal_subscriptions"

    subscription_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    stock_code: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('TRUE'))

    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('1'))


class SignalSubscriptionProjectionRecord(Base):
    __tablename__ = "signal_subscription_projections"

    subscription_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    shard_id: Mapped[str] = mapped_column(Text, nullable=False)

    stock_code: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)

    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
