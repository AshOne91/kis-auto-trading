from __future__ import annotations

from pydantic import BaseModel


class UpdateProfileRequest(BaseModel):
    investment_experience: str
    risk_tolerance: str
    investment_goal: str
    monthly_budget: float
