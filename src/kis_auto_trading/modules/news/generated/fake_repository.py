from kis_auto_trading.modules.news.generated.models import NewsArticle


class FakeNewsArticleRepository:
    def __init__(self) -> None:
        self._items: dict[str, NewsArticle] = {}

    async def find_by_id(
        self, source_key: str,
    ) -> NewsArticle | None:
        return self._items.get(source_key)

    async def save(
        self, aggregate: NewsArticle,
    ) -> None:
        self._items[aggregate.source_key] = aggregate
