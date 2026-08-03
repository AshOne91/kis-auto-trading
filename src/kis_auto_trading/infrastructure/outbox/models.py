from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from kis_auto_trading.infrastructure.database.base import Base


class OutboxEventRecord(Base):
    __tablename__ = 'outbox_events'

    event_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(200), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(200), nullable=False)
    routing_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class ProcessedMessageRecord(Base):
    __tablename__ = 'processed_messages'

    event_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
