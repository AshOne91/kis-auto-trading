from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NewsArticle:
    """A provider-neutral article matching the generated persistence contract."""

    source_key: str
    source_url: str
    provider: str
    title: str
    symbol: str
    published_at: datetime | None
    publisher: str | None
    content: str | None = None
