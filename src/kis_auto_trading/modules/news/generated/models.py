from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NewsArticle(BaseModel):
    source_key: str
    source_url: str
    provider: str
    title: str
    content: str | None = None
    symbol: str
    published_at: datetime
    publisher: str
    collected_at: datetime
