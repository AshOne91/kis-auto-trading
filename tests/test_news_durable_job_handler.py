from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from kis_auto_trading.application.durable_job_handler import (
    ApplicationDurableJobHandler,
)
from kis_auto_trading.infrastructure.durable_jobs.worker import DurableJobExecution
from kis_auto_trading.modules.news.models import NewsArticle
from kis_auto_trading.modules.news.yahoo import YahooFinanceNewsTimeoutError


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

        async def insert_many_returning_keys(self, articles, *, collected_at):
            del collected_at
            inserted.extend(articles)
            return [article.source_key for article in articles]

    class FakeDurableJobRepository:
        def __init__(self, session) -> None:
            del session

        async def request(self, **kwargs):
            assert kwargs["job_type"] == "news_index"
            assert kwargs["payload"] == {"source_keys": ["AAPL-key", "MSFT-key"]}
            return SimpleNamespace(job_id="index-job-1")

    monkeypatch.setattr(
        "kis_auto_trading.application.durable_job_handler.NewsArticleRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        "kis_auto_trading.application.durable_job_handler.DurableJobRepository",
        FakeDurableJobRepository,
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
        "index_job_id": "index-job-1",
    }
    assert [article.source_key for article in inserted] == ["AAPL-key", "MSFT-key"]
    assert registry.targets[0].store == "automation"


@pytest.mark.anyio
async def test_news_handler_requires_explicit_symbols() -> None:
    with pytest.raises(TypeError, match="symbols list"):
        await ApplicationDurableJobHandler(FakeRegistry(), FakeProvider()).handle(
            DurableJobExecution("job-1", "news_collection", "run-key", {})
        )


@pytest.mark.anyio
async def test_news_handler_schedules_retry_for_provider_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[dict[str, object]] = []

    class TimeoutProvider:
        async def collect(self, symbol: str) -> list[NewsArticle]:
            raise YahooFinanceNewsTimeoutError(f"timed out: {symbol}")

    class FakeDurableJobRepository:
        def __init__(self, session) -> None:
            del session

        async def request(self, **kwargs) -> SimpleNamespace:
            requested.append(kwargs)
            return SimpleNamespace(job_id="retry-job-1")

    monkeypatch.setattr(
        "kis_auto_trading.application.durable_job_handler.DurableJobRepository",
        FakeDurableJobRepository,
    )
    before_request = datetime.now(UTC)
    with pytest.raises(YahooFinanceNewsTimeoutError):
        await ApplicationDurableJobHandler(FakeRegistry(), TimeoutProvider()).handle(
            DurableJobExecution(
                job_id="job-1",
                job_type="news_collection",
                run_key="news:yahoo:test",
                payload={"symbols": ["aapl"]},
            )
        )
    after_request = datetime.now(UTC)

    assert requested[0]["job_type"] == "news_collection"
    assert requested[0]["run_key"] == "news:yahoo:test:retry:1"
    assert requested[0]["payload"] == {
        "symbols": ["AAPL"],
        "_news_retry_attempt": 1,
        "_news_retry_root_run_key": "news:yahoo:test",
    }
    assert before_request + timedelta(seconds=2) <= requested[0]["available_at"]
    assert requested[0]["available_at"] <= after_request + timedelta(seconds=2)


@pytest.mark.anyio
async def test_news_handler_stops_retrying_after_final_attempt(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class TimeoutProvider:
        async def collect(self, symbol: str) -> list[NewsArticle]:
            raise YahooFinanceNewsTimeoutError(f"timed out: {symbol}")

    class UnexpectedRepository:
        def __init__(self, session) -> None:
            raise AssertionError("final attempt must not schedule another retry")

    monkeypatch.setattr(
        "kis_auto_trading.application.durable_job_handler.DurableJobRepository",
        UnexpectedRepository,
    )
    caplog.set_level("ERROR")
    with pytest.raises(YahooFinanceNewsTimeoutError):
        await ApplicationDurableJobHandler(FakeRegistry(), TimeoutProvider()).handle(
            DurableJobExecution(
                job_id="job-3",
                job_type="news_collection",
                run_key="news:yahoo:test:retry:2",
                payload={
                    "symbols": ["aapl"],
                    "_news_retry_attempt": 2,
                    "_news_retry_root_run_key": "news:yahoo:test",
                },
            )
        )
    assert "news collection retries exhausted" in caplog.text
    assert "job_id=job-3" in caplog.text
    record = caplog.records[-1]
    assert record.event_type == "news_collection_retries_exhausted"
    assert record.job_id == "job-3"
    assert record.run_key == "news:yahoo:test:retry:2"
    assert record.attempt == 3
    assert record.max_attempts == 3


@pytest.mark.anyio
async def test_news_index_handler_reads_canonical_articles_before_indexing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = await FakeProvider().collect("AAPL")
    indexed: list[NewsArticle] = []

    class FakeRepository:
        def __init__(self, session) -> None:
            del session

        async def find_by_source_keys(self, source_keys):
            assert source_keys == ["AAPL-key"]
            return article

    class FakeIndexer:
        async def index(self, articles):
            indexed.extend(articles)
            return len(articles)

    monkeypatch.setattr(
        "kis_auto_trading.application.durable_job_handler.NewsArticleRepository",
        FakeRepository,
    )
    result = await ApplicationDurableJobHandler(
        FakeRegistry(), FakeProvider(), FakeIndexer()
    ).handle(
        DurableJobExecution(
            job_id="job-2",
            job_type="news_index",
            run_key="news-index:job-1",
            payload={"source_keys": ["AAPL-key"]},
        )
    )

    assert result == {
        "job_type": "news_index",
        "source_keys_requested": 1,
        "articles_indexed": 1,
    }
    assert indexed == article
