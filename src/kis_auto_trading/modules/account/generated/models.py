from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class UserProfile(BaseModel):
    user_id: UUID
    investment_experience: str = 'BEGINNER'
    risk_tolerance: str = 'MODERATE'
    investment_goal: str = 'GROWTH'
    monthly_budget: float = 0.0
    profile_completed: bool = False
