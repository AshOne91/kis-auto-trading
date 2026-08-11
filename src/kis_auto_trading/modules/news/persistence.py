from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.news.generated.sqlalchemy_models import NewsArticleRecord
from kis_auto_trading.modules.news.models import NewsArticle


class NewsArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_many(
        self, articles: list[NewsArticle], *, collected_at: datetime
    ) -> int:
        return len(
            await self.insert_many_returning_keys(articles, collected_at=collected_at)
        )

    async def insert_many_returning_keys(
        self, articles: list[NewsArticle], *, collected_at: datetime
    ) -> list[str]:
        unique_articles = {article.source_key: article for article in articles}
        if not unique_articles:
            return []

        statement = (
            insert(NewsArticleRecord)
            .values(
                [
                    {
                        "source_key": article.source_key,
                        "source_url": article.source_url,
                        "provider": article.provider,
                        "title": article.title,
                        "symbol": article.symbol,
                        "published_at": article.published_at,
                        "publisher": article.publisher,
                        "collected_at": collected_at,
                    }
                    for article in unique_articles.values()
                ]
            )
            .on_conflict_do_nothing(index_elements=["source_key"])
            .returning(NewsArticleRecord.source_key)
        )
        result = await self._session.execute(statement)
        return list(result.scalars())

    async def find_by_source_keys(self, source_keys: list[str]) -> list[NewsArticle]:
        if not source_keys:
            return []
        result = await self._session.execute(
            select(NewsArticleRecord).where(
                NewsArticleRecord.source_key.in_(source_keys)
            )
        )
        return [
            NewsArticle(
                source_key=record.source_key,
                source_url=record.source_url,
                provider=record.provider,
                title=record.title,
                symbol=record.symbol,
                published_at=record.published_at,
                publisher=record.publisher,
            )
            for record in result.scalars()
        ]
