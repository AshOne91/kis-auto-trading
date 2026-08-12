import asyncio
from datetime import UTC, datetime

import pytest

from kis_auto_trading.modules.news.yahoo import (
    YahooFinanceNewsProvider,
    YahooFinanceNewsProviderError,
    YahooFinanceNewsTimeoutError,
    normalize_yahoo_article,
)


def test_normalize_yahoo_article_supports_current_nested_payload() -> None:
    article = normalize_yahoo_article(
        "aapl",
        {
            "content": {
                "title": "Apple result",
                "canonicalUrl": {"url": "https://example.test/apple"},
                "pubDate": "2026-08-11T00:00:00Z",
                "provider": {"displayName": "Yahoo Finance"},
                "relatedTickers": ["MSFT", "AAPL"],
            }
        },
    )

    assert article is not None
    assert article.title == "Apple result"
    assert article.provider == "yahoo"
    assert article.symbol == "AAPL"
    assert article.publisher == "Yahoo Finance"
    assert article.published_at == datetime(2026, 8, 11, tzinfo=UTC)


def test_normalize_yahoo_article_skips_payload_without_title_or_url() -> None:
    assert normalize_yahoo_article("AAPL", {"title": "Missing URL"}) is None


@pytest.mark.anyio
async def test_provider_collects_without_network_when_ticker_is_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTicker:
        def __init__(self) -> None:
            self.news = [
                {"title": "Apple result", "link": "https://example.test/apple"}
            ]

    monkeypatch.setattr("yfinance.Ticker", lambda symbol: FakeTicker())

    articles = await YahooFinanceNewsProvider().collect("aapl")

    assert [article.title for article in articles] == ["Apple result"]
    assert articles[0].symbol == "AAPL"


@pytest.mark.anyio
async def test_provider_classifies_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_to_thread(*args: object, **kwargs: object) -> list[object]:
        await asyncio.sleep(0.05)
        return []

    monkeypatch.setattr("asyncio.to_thread", slow_to_thread)

    with pytest.raises(YahooFinanceNewsTimeoutError) as raised:
        await YahooFinanceNewsProvider(timeout_seconds=0.001).collect("AAPL")

    assert isinstance(raised.value.__cause__, TimeoutError)


@pytest.mark.anyio
async def test_provider_classifies_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_collect(symbol: str) -> list[object]:
        raise OSError("upstream unavailable")

    monkeypatch.setattr(
        YahooFinanceNewsProvider, "_collect", staticmethod(failing_collect)
    )

    with pytest.raises(YahooFinanceNewsProviderError) as raised:
        await YahooFinanceNewsProvider().collect("AAPL")

    assert isinstance(raised.value.__cause__, OSError)


def test_provider_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        YahooFinanceNewsProvider(timeout_seconds=0)
