from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class SignupRequest(BaseModel):
    email: str
    password: str


class SignupResponse(BaseModel):
    user_id: UUID
    email: str
    is_active: bool


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    user_id: UUID
    access_token: str
    token_type: str
