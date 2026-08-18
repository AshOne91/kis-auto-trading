from datetime import UTC, datetime

from kis_auto_trading.modules.news.yahoo import normalize_yahoo_article


def test_normalize_yahoo_article_uses_nested_content_and_canonical_url() -> None:
    article = normalize_yahoo_article(
        " aapl ",
        {
            "content": {
                "title": " Apple results ",
                "canonicalUrl": {"url": "https://example.test/articles/aapl"},
                "pubDate": "2026-08-19T09:30:00+00:00",
                "publisher": {"displayName": " Example News "},
                "summary": " Apple revenue exceeded expectations. ",
            }
        },
    )

    assert article is not None
    assert article.source_url == "https://example.test/articles/aapl"
    assert article.symbol == "AAPL"
    assert article.published_at == datetime(2026, 8, 19, 9, 30, tzinfo=UTC)
    assert article.publisher == "Example News"
    assert article.content == "Apple revenue exceeded expectations."


def test_normalize_yahoo_article_skips_records_without_title_or_url() -> None:
    assert normalize_yahoo_article("AAPL", {"link": "https://example.test"}) is None
    assert normalize_yahoo_article("AAPL", {"title": "Apple results"}) is None


def test_normalize_yahoo_article_falls_back_to_description_for_content() -> None:
    article = normalize_yahoo_article(
        "AAPL",
        {
            "title": "Apple results",
            "link": "https://example.test/articles/aapl",
            "description": "Apple reports stronger revenue.",
        },
    )

    assert article is not None
    assert article.content == "Apple reports stronger revenue."
