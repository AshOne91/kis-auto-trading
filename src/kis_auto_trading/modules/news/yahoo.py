import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256

import yfinance

from kis_auto_trading.modules.news.models import NewsArticle


class YahooFinanceNewsProvider:
    """Fetch and normalize Yahoo Finance news for one market symbol."""

    async def collect(self, symbol: str) -> list[NewsArticle]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")
        return await asyncio.to_thread(self._collect, normalized_symbol)

    @staticmethod
    def _collect(symbol: str) -> list[NewsArticle]:
        payloads = yfinance.Ticker(symbol).news or []
        return [
            article
            for payload in payloads
            if (article := normalize_yahoo_article(symbol, payload)) is not None
        ]


def normalize_yahoo_article(
    symbol: str, payload: Mapping[str, object]
) -> NewsArticle | None:
    """Return a stable article shape, skipping malformed provider payloads."""

    content = payload.get("content")
    values = content if isinstance(content, Mapping) else payload
    title = _string(values.get("title"))
    source_url = _string(values.get("link")) or _string(values.get("displayUrl"))
    canonical_url = values.get("canonicalUrl")
    if source_url is None and isinstance(canonical_url, Mapping):
        source_url = _string(canonical_url.get("url"))
    if title is None or source_url is None:
        return None

    return NewsArticle(
        source_key=sha256(source_url.encode()).hexdigest(),
        source_url=source_url,
        provider="yahoo",
        title=title,
        symbol=symbol.strip().upper(),
        published_at=_published_at(
            values.get("providerPublishTime") or values.get("pubDate")
        ),
        publisher=_publisher(values.get("publisher") or values.get("provider")),
    )


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _published_at(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    return None


def _publisher(value: object) -> str | None:
    if isinstance(value, Mapping):
        return _string(value.get("displayName")) or _string(value.get("name"))
    return _string(value)
