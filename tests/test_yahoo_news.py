from datetime import UTC, datetime

import pytest

from kis_auto_trading.modules.news.yahoo import (
    YahooFinanceNewsProvider,
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
