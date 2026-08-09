from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from kis_auto_trading.infrastructure.database.base import Base


class DurableJobRecord(Base):
    __tablename__ = 'durable_jobs'
    __table_args__ = (
        UniqueConstraint('job_type', 'run_key', name='uq_durable_jobs_type_run_key'),
    )

    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    run_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
