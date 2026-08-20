import logging
from datetime import UTC, datetime, timedelta

import httpx

from kis_auto_trading.application.market_price_snapshots import (
    save_market_price_snapshot,
)
from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.durable_jobs.contracts import JOB_DEFINITIONS
from kis_auto_trading.infrastructure.durable_jobs.repository import DurableJobRepository
from kis_auto_trading.infrastructure.durable_jobs.worker import DurableJobExecution
from kis_auto_trading.infrastructure.kis_market_data import KisMarketDataClient
from kis_auto_trading.modules.news.persistence import NewsArticleRepository
from kis_auto_trading.modules.news.search import NewsSearchIndexer
from kis_auto_trading.modules.news.yahoo import (
    YahooFinanceNewsError,
    YahooFinanceNewsProvider,
)
from kis_auto_trading.modules.operations.durable_job_history_search import (
    DurableJobHistorySearchIndexer,
)

MAX_NEWS_DURABLE_JOB_ATTEMPTS = 3
logger = logging.getLogger(__name__)


class ApplicationDurableJobHandler:
    def __init__(
        self,
        session_registry: AsyncSessionRegistry,
        provider: YahooFinanceNewsProvider | None = None,
        indexer: NewsSearchIndexer | None = None,
        durable_job_history_indexer: DurableJobHistorySearchIndexer | None = None,
        market_data_client: KisMarketDataClient | None = None,
    ) -> None:
        self._session_registry = session_registry
        self._provider = provider or YahooFinanceNewsProvider()
        self._indexer = indexer
        self._durable_job_history_indexer = durable_job_history_indexer
        self._market_data_client = market_data_client

    async def handle(
        self, execution: DurableJobExecution
    ) -> dict[str, object] | None:
        if execution.job_type == "news_collection":
            return await self._collect_news(execution)
        if execution.job_type == "news_index":
            return await self._index_news(execution)
        if execution.job_type == "durable_job_history_index":
            return await self._index_durable_job_history(execution)
        if execution.job_type == "market_price_snapshot":
            return await self._collect_market_price_snapshot(execution)
        raise ValueError(f"unsupported durable job type: {execution.job_type}")

    async def _collect_market_price_snapshot(
        self, execution: DurableJobExecution
    ) -> dict[str, object]:
        stock_code = _market_price_stock_code_from_payload(execution.payload)
        client = self._market_data_client or KisMarketDataClient.from_environment()
        try:
            price = await client.get_domestic_stock_price(stock_code)
            snapshot = await save_market_price_snapshot(self._session_registry, price)
        finally:
            if self._market_data_client is None:
                await client.aclose()
        return {
            "job_type": execution.job_type,
            "stock_code": price.stock_code,
            "snapshot_id": str(snapshot.snapshot_id),
        }

    async def _collect_news(
        self, execution: DurableJobExecution
    ) -> dict[str, object]:
        symbols = _symbols_from_payload(execution.payload)
        articles = []
        try:
            for symbol in symbols:
                articles.extend(await self._provider.collect(symbol))
        except YahooFinanceNewsError:
            await self._request_news_retry(execution, {"symbols": symbols})
            raise

        async with self._session_registry.session(
            ShardTarget(store="automation")
        ) as session:
            source_keys = await NewsArticleRepository(session).insert_many_returning_keys(
                articles, collected_at=datetime.now(UTC)
            )
            index_job_id: str | None = None
            indexing_status = "skipped"
            if self._indexing_enabled():
                index_job = await DurableJobRepository(session).request(
                    job_type="news_index",
                    run_key=f"news-index:{execution.job_id}",
                    payload={"source_keys": source_keys},
                )
                index_job_id = index_job.job_id
                indexing_status = "requested"
            else:
                self._log_indexing_skipped(execution)
        return {
            "job_type": execution.job_type,
            "symbols": symbols,
            "articles_collected": len(articles),
            "articles_inserted": len(source_keys),
            "index_job_id": index_job_id,
            "indexing_status": indexing_status,
        }

    async def _request_news_retry(
        self, execution: DurableJobExecution, payload: dict[str, object]
    ) -> None:
        attempt = _news_retry_attempt(execution.payload)
        if attempt >= MAX_NEWS_DURABLE_JOB_ATTEMPTS - 1:
            logger.error(
                "%s retries exhausted: job_id=%s run_key=%s attempt=%s",
                execution.job_type.replace("_", " "),
                execution.job_id,
                execution.run_key,
                attempt + 1,
                extra={
                    "event_type": f"{execution.job_type}_retries_exhausted",
                    "job_type": execution.job_type,
                    "job_id": execution.job_id,
                    "run_key": execution.run_key,
                    "attempt": attempt + 1,
                    "max_attempts": MAX_NEWS_DURABLE_JOB_ATTEMPTS,
                },
            )
            return

        retry_attempt = attempt + 1
        root_run_key = _news_retry_root_run_key(execution)
        retry_payload = {
            **payload,
            "_news_retry_attempt": retry_attempt,
            "_news_retry_root_run_key": root_run_key,
        }
        async with self._session_registry.session(
            ShardTarget(store="automation")
        ) as session:
            await DurableJobRepository(session).request(
                job_type=execution.job_type,
                run_key=f"{root_run_key}:retry:{retry_attempt}",
                payload=retry_payload,
                available_at=datetime.now(UTC) + timedelta(seconds=2**retry_attempt),
            )

    async def _index_news(
        self, execution: DurableJobExecution
    ) -> dict[str, object]:
        source_keys = _source_keys_from_payload(execution.payload)
        if not self._indexing_enabled():
            self._log_indexing_skipped(execution)
            return {
                "job_type": execution.job_type,
                "source_keys_requested": len(source_keys),
                "articles_indexed": 0,
                "indexing_status": "skipped",
            }
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
        try:
            indexed = await indexer.index(articles)
        except httpx.HTTPError as error:
            if _is_transient_search_error(error):
                await self._request_news_retry(execution, {"source_keys": source_keys})
            raise
        return {
            "job_type": execution.job_type,
            "source_keys_requested": len(source_keys),
            "articles_indexed": indexed,
        }

    async def _index_durable_job_history(
        self, execution: DurableJobExecution
    ) -> dict[str, object]:
        history_job_type, limit = _history_request_from_payload(execution.payload)
        if not self._durable_job_history_indexing_enabled():
            self._log_durable_job_history_indexing_skipped(execution, history_job_type)
            return {
                "job_type": execution.job_type,
                "history_job_type": history_job_type,
                "records_indexed": 0,
                "indexing_status": "skipped",
            }
        async with self._session_registry.session(
            ShardTarget(store="automation")
        ) as session:
            records = await DurableJobRepository(session).list_recent(
                job_type=history_job_type, limit=limit
            )
        indexer = (
            self._durable_job_history_indexer
            or DurableJobHistorySearchIndexer.from_environment()
        )
        indexed = await indexer.index(records)
        return {
            "job_type": execution.job_type,
            "history_job_type": history_job_type,
            "records_indexed": indexed,
        }

    def _indexing_enabled(self) -> bool:
        return self._indexer is not None or NewsSearchIndexer.is_configured_from_environment()

    def _durable_job_history_indexing_enabled(self) -> bool:
        return (
            self._durable_job_history_indexer is not None
            or DurableJobHistorySearchIndexer.is_configured_from_environment()
        )

    @staticmethod
    def _log_indexing_skipped(execution: DurableJobExecution) -> None:
        logger.info(
            "news indexing skipped because the RAG profile is not configured",
            extra={
                "event_type": "news_index_skipped",
                "job_id": execution.job_id,
                "run_key": execution.run_key,
            },
        )

    @staticmethod
    def _log_durable_job_history_indexing_skipped(
        execution: DurableJobExecution, history_job_type: str
    ) -> None:
        logger.info(
            "durable job history indexing skipped because the RAG profile is not configured",
            extra={
                "event_type": "durable_job_history_index_skipped",
                "job_id": execution.job_id,
                "run_key": execution.run_key,
                "history_job_type": history_job_type,
            },
        )


def validate_durable_job_payload(job_type: str, payload: dict[str, object]) -> None:
    if job_type == "market_price_snapshot":
        _market_price_stock_code_from_payload(payload)


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


def _market_price_stock_code_from_payload(payload: dict[str, object]) -> str:
    stock_code = payload.get("stock_code")
    if not isinstance(stock_code, str):
        raise TypeError("market_price_snapshot payload requires a stock_code string")
    normalized = stock_code.strip()
    if (
        len(normalized) != 6
        or not normalized.isascii()
        or not normalized.isdecimal()
    ):
        raise ValueError(
            "market_price_snapshot stock_code must be a six-digit domestic stock code"
        )
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


def _history_request_from_payload(payload: dict[str, object]) -> tuple[str, int]:
    job_type = payload.get("history_job_type")
    if not isinstance(job_type, str) or job_type not in JOB_DEFINITIONS:
        raise ValueError("history_job_type must name a configured durable job")
    limit = payload.get("limit", 100)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("history limit must be between 1 and 100")
    return job_type, limit


def _news_retry_attempt(payload: dict[str, object]) -> int:
    attempt = payload.get("_news_retry_attempt", 0)
    return attempt if isinstance(attempt, int) and attempt >= 0 else 0


def _news_retry_root_run_key(execution: DurableJobExecution) -> str:
    root = execution.payload.get("_news_retry_root_run_key")
    return root if isinstance(root, str) and root else execution.run_key


def _is_transient_search_error(error: httpx.HTTPError) -> bool:
    if isinstance(error, httpx.RequestError):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return (
            error.response.status_code in {408, 429}
            or error.response.status_code >= 500
        )
    return False


def create_durable_job_handler(
    session_registry: AsyncSessionRegistry,
) -> ApplicationDurableJobHandler:
    return ApplicationDurableJobHandler(session_registry)
