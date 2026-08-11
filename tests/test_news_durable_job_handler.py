from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest

from kis_auto_trading.application.durable_job_handler import (
    ApplicationDurableJobHandler,
)
from kis_auto_trading.infrastructure.durable_jobs.worker import DurableJobExecution
from kis_auto_trading.modules.news.models import NewsArticle


class FakeProvider:
    async def collect(self, symbol: str) -> list[NewsArticle]:
        return [
            NewsArticle(
                source_key=f"{symbol}-key",
                source_url=f"https://example.test/{symbol}",
                provider="test",
                title=f"{symbol} headline",
                symbol=symbol,
                published_at=datetime(2026, 8, 11, tzinfo=UTC),
                publisher="test",
            )
        ]


class FakeRegistry:
    def __init__(self) -> None:
        self.targets = []

    @asynccontextmanager
    async def session(self, target):
        self.targets.append(target)
        yield object()


@pytest.mark.anyio
async def test_news_handler_collects_and_uses_global_automation_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inserted: list[NewsArticle] = []

    class FakeRepository:
        def __init__(self, session) -> None:
            del session

        async def insert_many(self, articles, *, collected_at):
            del collected_at
            inserted.extend(articles)
            return len(articles)

    monkeypatch.setattr(
        "kis_auto_trading.application.durable_job_handler.NewsArticleRepository",
        FakeRepository,
    )
    registry = FakeRegistry()
    result = await ApplicationDurableJobHandler(registry, FakeProvider()).handle(
        DurableJobExecution(
            job_id="job-1",
            job_type="news_collection",
            run_key="news:yahoo:test",
            payload={"symbols": ["aapl", "msft", "aapl"]},
        )
    )

    assert result == {
        "job_type": "news_collection",
        "symbols": ["AAPL", "MSFT"],
        "articles_collected": 2,
        "articles_inserted": 2,
    }
    assert [article.source_key for article in inserted] == ["AAPL-key", "MSFT-key"]
    assert registry.targets[0].store == "automation"


@pytest.mark.anyio
async def test_news_handler_requires_explicit_symbols() -> None:
    with pytest.raises(TypeError, match="symbols list"):
        await ApplicationDurableJobHandler(FakeRegistry(), FakeProvider()).handle(
            DurableJobExecution("job-1", "news_collection", "run-key", {})
        )
