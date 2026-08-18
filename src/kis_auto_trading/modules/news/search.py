import asyncio
import json
import os
from collections.abc import Sequence
from enum import StrEnum

import httpx

from kis_auto_trading.modules.news.models import NewsArticle

NEWS_INDEX = "news-articles-v1"


class SearchBackend(StrEnum):
    ELASTICSEARCH = "elasticsearch"
    OPENSEARCH = "opensearch"


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
        self._search_backend = SearchBackend(search_backend)
        self._search_url = search_url.rstrip("/")
        self._ollama_url = ollama_url.rstrip("/")
        self._embedding_model = embedding_model
        self._transport = transport

    @classmethod
    def from_environment(cls) -> "NewsSearchIndexer":
        search_url = os.getenv("RAG_SEARCH_URL") or os.environ["RAG_ELASTICSEARCH_URL"]
        return cls(
            ollama_url=os.environ["RAG_OLLAMA_URL"],
            embedding_model=os.environ["RAG_EMBEDDING_MODEL"],
            search_url=search_url,
            search_backend=os.getenv("RAG_SEARCH_BACKEND", SearchBackend.ELASTICSEARCH),
        )

    async def index(self, articles: Sequence[NewsArticle]) -> int:
        if not articles:
            return 0

        contents = [self._content(article) for article in articles]
        embeddings = await self._embed(contents)
        if len(embeddings) != len(articles):
            raise ValueError("embedding response does not match indexed articles")
        await self._ensure_index(dimensions=len(embeddings[0]))

        lines: list[str] = []
        for article, embedding in zip(articles, embeddings, strict=True):
            lines.append(
                f'{{"index":{{"_index":"{NEWS_INDEX}","_id":"{article.source_key}"}}}}'
            )
            lines.append(
                json.dumps(
                    {
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
                        "embedding": embedding,
                    },
                    separators=(",", ":"),
                )
            )
        async with self._client() as client:
            response = await client.post(
                f"{self._search_url}/_bulk",
                content="\n".join(lines) + "\n",
                headers={"content-type": "application/x-ndjson"},
            )
        response.raise_for_status()
        if response.json()["errors"]:
            raise RuntimeError("search backend rejected one or more news documents")
        return len(articles)

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, object]]:
        embedding = (await self._embed([query]))[0]
        candidate_count = max(limit * 2, 20)
        async with self._client() as client:
            keyword_response, vector_response = await asyncio.gather(
                client.post(
                    f"{self._search_url}/{NEWS_INDEX}/_search",
                    json={
                        "size": candidate_count,
                        "query": {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "title^3",
                                    "content",
                                    "symbol^2",
                                    "publisher",
                                ],
                            }
                        },
                    },
                ),
                client.post(
                    f"{self._search_url}/{NEWS_INDEX}/_search",
                    json=self._vector_search_payload(embedding, candidate_count),
                ),
            )
        keyword_response.raise_for_status()
        vector_response.raise_for_status()

        sources: dict[str, dict[str, object]] = {}
        scores: dict[str, float] = {}
        for response in (keyword_response, vector_response):
            for rank, hit in enumerate(response.json()["hits"]["hits"], start=1):
                source = hit["_source"]
                source_key = str(source["source_key"])
                sources[source_key] = source
                scores[source_key] = scores.get(source_key, 0.0) + 1.0 / (60 + rank)

        ranked_keys = sorted(
            scores, key=lambda source_key: (-scores[source_key], source_key)
        )
        return [sources[source_key] for source_key in ranked_keys[:limit]]

    async def _embed(self, inputs: Sequence[str]) -> list[list[float]]:
        async with self._client() as client:
            response = await client.post(
                f"{self._ollama_url}/api/embed",
                json={"model": self._embedding_model, "input": list(inputs)},
            )
        response.raise_for_status()
        embeddings = response.json()["embeddings"]
        if (
            not embeddings
            or not embeddings[0]
            or not all(isinstance(vector, list) for vector in embeddings)
        ):
            raise ValueError("Ollama returned no embeddings")
        return embeddings

    async def _ensure_index(self, *, dimensions: int) -> None:
        async with self._client() as client:
            exists = await client.head(f"{self._search_url}/{NEWS_INDEX}")
            if exists.status_code == 200:
                return
            if exists.status_code != 404:
                exists.raise_for_status()
            created = await client.put(
                f"{self._search_url}/{NEWS_INDEX}",
                json=self._index_mapping(dimensions),
            )
        if created.status_code not in {200, 201, 400}:
            created.raise_for_status()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=30.0)

    def _vector_search_payload(
        self, embedding: list[float], candidate_count: int
    ) -> dict[str, object]:
        if self._search_backend is SearchBackend.OPENSEARCH:
            return {
                "size": candidate_count,
                "query": {
                    "knn": {"embedding": {"vector": embedding, "k": candidate_count}}
                },
            }
        return {
            "size": candidate_count,
            "knn": {
                "field": "embedding",
                "query_vector": embedding,
                "k": candidate_count,
                "num_candidates": 100,
            },
        }

    def _index_mapping(self, dimensions: int) -> dict[str, object]:
        properties: dict[str, object] = {
            "source_key": {"type": "keyword"},
            "source_url": {"type": "keyword", "index": False},
            "provider": {"type": "keyword"},
            "title": {"type": "text"},
            "content": {"type": "text"},
            "symbol": {"type": "keyword"},
            "published_at": {"type": "date"},
            "publisher": {"type": "keyword"},
        }
        if self._search_backend is SearchBackend.OPENSEARCH:
            properties["embedding"] = {
                "type": "knn_vector",
                "dimension": dimensions,
                "method": {
                    "name": "hnsw",
                    "engine": "faiss",
                    "space_type": "cosinesimil",
                },
            }
            return {
                "settings": {"index": {"knn": True}},
                "mappings": {"properties": properties},
            }
        properties["embedding"] = {
            "type": "dense_vector",
            "dims": dimensions,
            "similarity": "cosine",
        }
        return {"mappings": {"properties": properties}}

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
