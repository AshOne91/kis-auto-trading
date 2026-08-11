import json
import os
from collections.abc import Sequence

import httpx

from kis_auto_trading.modules.news.models import NewsArticle

NEWS_INDEX = "news-articles-v1"


class NewsSearchIndexer:
    """Indexes canonical news records for Elasticsearch native hybrid retrieval."""

    def __init__(
        self,
        *,
        elasticsearch_url: str,
        ollama_url: str,
        embedding_model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._elasticsearch_url = elasticsearch_url.rstrip("/")
        self._ollama_url = ollama_url.rstrip("/")
        self._embedding_model = embedding_model
        self._transport = transport

    @classmethod
    def from_environment(cls) -> "NewsSearchIndexer":
        return cls(
            elasticsearch_url=os.environ["RAG_ELASTICSEARCH_URL"],
            ollama_url=os.environ["RAG_OLLAMA_URL"],
            embedding_model=os.environ["RAG_EMBEDDING_MODEL"],
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
            lines.append(f'{{"index":{{"_index":"{NEWS_INDEX}","_id":"{article.source_key}"}}}}')
            lines.append(
                json.dumps(
                    {
                        "source_key": article.source_key,
                        "source_url": article.source_url,
                        "provider": article.provider,
                        "title": article.title,
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
                f"{self._elasticsearch_url}/_bulk",
                content="\n".join(lines) + "\n",
                headers={"content-type": "application/x-ndjson"},
            )
        response.raise_for_status()
        if response.json()["errors"]:
            raise RuntimeError("Elasticsearch rejected one or more news documents")
        return len(articles)

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, object]]:
        embedding = (await self._embed([query]))[0]
        async with self._client() as client:
            response = await client.post(
                f"{self._elasticsearch_url}/{NEWS_INDEX}/_search",
                json={
                    "size": limit,
                    "retriever": {
                        "rrf": {
                            "retrievers": [
                                {
                                    "standard": {
                                        "query": {
                                            "multi_match": {
                                                "query": query,
                                                "fields": ["title^3", "symbol^2", "publisher"],
                                            }
                                        }
                                    }
                                },
                                {
                                    "knn": {
                                        "field": "embedding",
                                        "query_vector": embedding,
                                        "k": max(limit * 2, 20),
                                        "num_candidates": 100,
                                    }
                                },
                            ]
                        }
                    },
                },
            )
        response.raise_for_status()
        return [hit["_source"] for hit in response.json()["hits"]["hits"]]

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
            exists = await client.head(f"{self._elasticsearch_url}/{NEWS_INDEX}")
            if exists.status_code == 200:
                return
            if exists.status_code != 404:
                exists.raise_for_status()
            created = await client.put(
                f"{self._elasticsearch_url}/{NEWS_INDEX}",
                json={
                    "mappings": {
                        "properties": {
                            "source_key": {"type": "keyword"},
                            "source_url": {"type": "keyword", "index": False},
                            "provider": {"type": "keyword"},
                            "title": {"type": "text"},
                            "symbol": {"type": "keyword"},
                            "published_at": {"type": "date"},
                            "publisher": {"type": "keyword"},
                            "embedding": {
                                "type": "dense_vector",
                                "dims": dimensions,
                                "similarity": "cosine",
                            },
                        }
                    }
                },
            )
        if created.status_code not in {200, 201, 400}:
            created.raise_for_status()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=30.0)

    @staticmethod
    def _content(article: NewsArticle) -> str:
        return "\n".join(
            value for value in (article.title, article.symbol, article.publisher) if value
        )
