import logging
from datetime import UTC, datetime, timedelta

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.durable_jobs.repository import DurableJobRepository
from kis_auto_trading.infrastructure.durable_jobs.worker import DurableJobExecution
from kis_auto_trading.modules.news.persistence import NewsArticleRepository
from kis_auto_trading.modules.news.search import NewsSearchIndexer
from kis_auto_trading.modules.news.yahoo import (
    YahooFinanceNewsError,
    YahooFinanceNewsProvider,
)

MAX_NEWS_COLLECTION_ATTEMPTS = 3
logger = logging.getLogger(__name__)


class ApplicationDurableJobHandler:
    def __init__(
        self,
        session_registry: AsyncSessionRegistry,
        provider: YahooFinanceNewsProvider | None = None,
        indexer: NewsSearchIndexer | None = None,
    ) -> None:
        self._session_registry = session_registry
        self._provider = provider or YahooFinanceNewsProvider()
        self._indexer = indexer

    async def handle(
        self, execution: DurableJobExecution
    ) -> dict[str, object] | None:
        if execution.job_type == "news_collection":
            return await self._collect_news(execution)
        if execution.job_type == "news_index":
            return await self._index_news(execution)
        raise ValueError(f"unsupported durable job type: {execution.job_type}")

    async def _collect_news(
        self, execution: DurableJobExecution
    ) -> dict[str, object]:
        symbols = _symbols_from_payload(execution.payload)
        articles = []
        try:
            for symbol in symbols:
                articles.extend(await self._provider.collect(symbol))
        except YahooFinanceNewsError:
            await self._request_news_retry(execution, symbols)
            raise

        async with self._session_registry.session(
            ShardTarget(store="automation")
        ) as session:
            source_keys = await NewsArticleRepository(session).insert_many_returning_keys(
                articles, collected_at=datetime.now(UTC)
            )
            index_job = await DurableJobRepository(session).request(
                job_type="news_index",
                run_key=f"news-index:{execution.job_id}",
                payload={"source_keys": source_keys},
            )
        return {
            "job_type": execution.job_type,
            "symbols": symbols,
            "articles_collected": len(articles),
            "articles_inserted": len(source_keys),
            "index_job_id": index_job.job_id,
        }

    async def _request_news_retry(
        self, execution: DurableJobExecution, symbols: list[str]
    ) -> None:
        attempt = _news_retry_attempt(execution.payload)
        if attempt >= MAX_NEWS_COLLECTION_ATTEMPTS - 1:
            logger.error(
                "news collection retries exhausted: job_id=%s run_key=%s attempt=%s",
                execution.job_id,
                execution.run_key,
                attempt + 1,
                extra={
                    "event_type": "news_collection_retries_exhausted",
                    "job_type": execution.job_type,
                    "job_id": execution.job_id,
                    "run_key": execution.run_key,
                    "attempt": attempt + 1,
                    "max_attempts": MAX_NEWS_COLLECTION_ATTEMPTS,
                },
            )
            return

        retry_attempt = attempt + 1
        root_run_key = _news_retry_root_run_key(execution)
        retry_payload: dict[str, object] = {
            "symbols": symbols,
            "_news_retry_attempt": retry_attempt,
            "_news_retry_root_run_key": root_run_key,
        }
        async with self._session_registry.session(
            ShardTarget(store="automation")
        ) as session:
            await DurableJobRepository(session).request(
                job_type="news_collection",
                run_key=f"{root_run_key}:retry:{retry_attempt}",
                payload=retry_payload,
                available_at=datetime.now(UTC) + timedelta(seconds=2**retry_attempt),
            )

    async def _index_news(
        self, execution: DurableJobExecution
    ) -> dict[str, object]:
        source_keys = _source_keys_from_payload(execution.payload)
        async with self._session_registry.session(
            ShardTarget(store="automation")
        ) as session:
            articles = await NewsArticleRepository(session).find_by_source_keys(source_keys)
        if not articles:
            return {
                "job_type": execution.job_type,
                "source_keys_requested": len(source_keys),
                "articles_indexed": 0,
            }
        indexer = self._indexer or NewsSearchIndexer.from_environment()
        indexed = await indexer.index(articles)
        return {
            "job_type": execution.job_type,
            "source_keys_requested": len(source_keys),
            "articles_indexed": indexed,
        }


def _symbols_from_payload(payload: dict[str, object]) -> list[str]:
    symbols = payload.get("symbols")
    if not isinstance(symbols, list):
        raise TypeError("news_collection payload requires a symbols list")
    normalized = list(
        dict.fromkeys(
            symbol.strip().upper()
            for symbol in symbols
            if isinstance(symbol, str) and symbol.strip()
        )
    )
    if not normalized:
        raise ValueError("news_collection payload requires at least one symbol")
    return normalized


def _source_keys_from_payload(payload: dict[str, object]) -> list[str]:
    source_keys = payload.get("source_keys")
    if not isinstance(source_keys, list):
        raise TypeError("news_index payload requires a source_keys list")
    normalized = list(
        dict.fromkeys(
            source_key.strip()
            for source_key in source_keys
            if isinstance(source_key, str) and source_key.strip()
        )
    )
    if not normalized:
        raise ValueError("news_index payload requires at least one source key")
    return normalized


def _news_retry_attempt(payload: dict[str, object]) -> int:
    attempt = payload.get("_news_retry_attempt", 0)
    return attempt if isinstance(attempt, int) and attempt >= 0 else 0


def _news_retry_root_run_key(execution: DurableJobExecution) -> str:
    root = execution.payload.get("_news_retry_root_run_key")
    return root if isinstance(root, str) and root else execution.run_key


def create_durable_job_handler(
    session_registry: AsyncSessionRegistry,
) -> ApplicationDurableJobHandler:
    return ApplicationDurableJobHandler(session_registry)
