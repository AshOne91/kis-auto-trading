from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.news.generated.models import NewsArticle
from kis_auto_trading.modules.news.generated.sqlalchemy_models import NewsArticleRecord


class SQLAlchemyNewsArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, source_key: str,
    ) -> NewsArticle | None:
        record = await self._session.get(
            NewsArticleRecord, source_key
        )
        if record is None:
            return None
        return NewsArticle(
            source_key=record.source_key,
            source_url=record.source_url,
            provider=record.provider,
            title=record.title,
            content=record.content,
            symbol=record.symbol,
            published_at=record.published_at,
            publisher=record.publisher,
            collected_at=record.collected_at
        )

    async def save(
        self, aggregate: NewsArticle,
    ) -> None:
        record = NewsArticleRecord(
            source_key=aggregate.source_key,
            source_url=aggregate.source_url,
            provider=aggregate.provider,
            title=aggregate.title,
            content=aggregate.content,
            symbol=aggregate.symbol,
            published_at=aggregate.published_at,
            publisher=aggregate.publisher,
            collected_at=aggregate.collected_at
        )
        await self._session.merge(record)
