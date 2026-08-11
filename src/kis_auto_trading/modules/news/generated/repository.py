from typing import Protocol

from kis_auto_trading.modules.news.generated.models import NewsArticle


class NewsArticleRepository(Protocol):
    async def find_by_id(
        self, source_key: str,
    ) -> NewsArticle | None: ...
    async def save(
        self, aggregate: NewsArticle,
    ) -> None: ...
