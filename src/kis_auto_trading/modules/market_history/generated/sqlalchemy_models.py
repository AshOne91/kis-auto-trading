from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from kis_auto_trading.infrastructure.database.base import Base


class DomesticDailyCandleRecord(Base):
    __tablename__ = "domestic_daily_candles"

    candle_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    stock_code: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    trading_date: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    open_price: Mapped[str] = mapped_column(Text, nullable=False)

    high_price: Mapped[str] = mapped_column(Text, nullable=False)

    low_price: Mapped[str] = mapped_column(Text, nullable=False)

    close_price: Mapped[str] = mapped_column(Text, nullable=False)

    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
