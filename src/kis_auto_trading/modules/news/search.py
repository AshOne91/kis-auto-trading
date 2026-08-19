import os
from collections.abc import Sequence

import httpx

from kis_auto_trading.modules.news.models import NewsArticle
from kis_auto_trading.modules.search.hybrid import HybridSearchIndex, SearchBackend

NEWS_INDEX = "news-articles-v1"


class NewsSearchIndexer:
    """Indexes canonical news records for the configured hybrid-search backend."""

    def __init__(
        self,
        *,
        ollama_url: str,
        embedding_model: str,
        elasticsearch_url: str | None = None,
        search_url: str | None = None,
        search_backend: SearchBackend | str = SearchBackend.ELASTICSEARCH,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if search_url is None:
            if elasticsearch_url is None:
                raise ValueError("search_url is required")
            search_url = elasticsearch_url
        self._index = HybridSearchIndex(
            index_name=NEWS_INDEX,
            source_id_field="source_key",
            properties={
                "source_key": {"type": "keyword"},
                "source_url": {"type": "keyword", "index": False},
                "provider": {"type": "keyword"},
                "title": {"type": "text"},
                "content": {"type": "text"},
                "symbol": {"type": "keyword"},
                "published_at": {"type": "date"},
                "publisher": {"type": "keyword"},
            },
            keyword_fields=["title^3", "content", "symbol^2", "publisher"],
            ollama_url=ollama_url,
            embedding_model=embedding_model,
            search_url=search_url,
            search_backend=search_backend,
            transport=transport,
        )

    @classmethod
    def from_environment(cls) -> "NewsSearchIndexer":
        search_url = os.getenv("RAG_SEARCH_URL") or os.environ["RAG_ELASTICSEARCH_URL"]
        return cls(
            ollama_url=os.environ["RAG_OLLAMA_URL"],
            embedding_model=os.environ["RAG_EMBEDDING_MODEL"],
            search_url=search_url,
            search_backend=os.getenv("RAG_SEARCH_BACKEND", SearchBackend.ELASTICSEARCH),
        )

    @classmethod
    def is_configured_from_environment(cls) -> bool:
        return bool(
            (os.getenv("RAG_SEARCH_URL") or os.getenv("RAG_ELASTICSEARCH_URL"))
            and os.getenv("RAG_OLLAMA_URL")
            and os.getenv("RAG_EMBEDDING_MODEL")
        )

    async def index(self, articles: Sequence[NewsArticle]) -> int:
        return await self._index.index(
            [(self._source(article), self._content(article)) for article in articles]
        )

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, object]]:
        return await self._index.search(query, limit=limit)

    @staticmethod
    def _source(article: NewsArticle) -> dict[str, object]:
        return {
            "source_key": article.source_key,
            "source_url": article.source_url,
            "provider": article.provider,
            "title": article.title,
            "content": article.content,
            "symbol": article.symbol,
            "published_at": (
                article.published_at.isoformat()
                if article.published_at is not None
                else None
            ),
            "publisher": article.publisher,
        }

    @staticmethod
    def _content(article: NewsArticle) -> str:
        return "\n".join(
            value
            for value in (
                article.title,
                article.content,
                article.symbol,
                article.publisher,
            )
            if value
        )
