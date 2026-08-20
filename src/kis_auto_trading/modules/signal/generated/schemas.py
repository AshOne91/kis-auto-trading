from __future__ import annotations

from pydantic import BaseModel


class SubscribeRequest(BaseModel):
    stock_code: str


class UnsubscribeRequest(BaseModel):
    stock_code: str
