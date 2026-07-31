from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, Float, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from kis_auto_trading.infrastructure.database.base import Base


class UserProfileRecord(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)

    investment_experience: Mapped[str] = mapped_column(Text, nullable=False)

    risk_tolerance: Mapped[str] = mapped_column(Text, nullable=False)

    investment_goal: Mapped[str] = mapped_column(Text, nullable=False)

    monthly_budget: Mapped[float] = mapped_column(Float, nullable=False)

    profile_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('FALSE'))
