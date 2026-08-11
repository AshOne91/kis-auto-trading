from datetime import UTC, datetime

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.durable_jobs.worker import DurableJobExecution
from kis_auto_trading.modules.news.persistence import NewsArticleRepository
from kis_auto_trading.modules.news.yahoo import YahooFinanceNewsProvider


class ApplicationDurableJobHandler:
    def __init__(
        self,
        session_registry: AsyncSessionRegistry,
        provider: YahooFinanceNewsProvider | None = None,
    ) -> None:
        self._session_registry = session_registry
        self._provider = provider or YahooFinanceNewsProvider()

    async def handle(
        self, execution: DurableJobExecution
    ) -> dict[str, object] | None:
        if execution.job_type != "news_collection":
            raise ValueError(f"unsupported durable job type: {execution.job_type}")

        symbols = _symbols_from_payload(execution.payload)
        articles = []
        for symbol in symbols:
            articles.extend(await self._provider.collect(symbol))

        async with self._session_registry.session(
            ShardTarget(store="automation")
        ) as session:
            inserted = await NewsArticleRepository(session).insert_many(
                articles, collected_at=datetime.now(UTC)
            )
        return {
            "job_type": execution.job_type,
            "symbols": symbols,
            "articles_collected": len(articles),
            "articles_inserted": inserted,
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


def create_durable_job_handler(
    session_registry: AsyncSessionRegistry,
) -> ApplicationDurableJobHandler:
    return ApplicationDurableJobHandler(session_registry)
