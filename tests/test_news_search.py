import json
from datetime import UTC, datetime

import httpx
import pytest

from kis_auto_trading.modules.news.models import NewsArticle
from kis_auto_trading.modules.news.search import NEWS_INDEX, NewsSearchIndexer


def _article() -> NewsArticle:
    return NewsArticle(
        source_key="article-1",
        source_url="https://example.test/article-1",
        provider="test",
        title="AAPL earnings rise",
        symbol="AAPL",
        published_at=datetime(2026, 8, 11, tzinfo=UTC),
        publisher="test",
    )


@pytest.mark.anyio
async def test_index_creates_native_hybrid_mapping_and_bulk_upserts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
        if request.method == "HEAD":
            return httpx.Response(404)
        if request.method == "PUT":
            return httpx.Response(200, json={"acknowledged": True})
        if request.url.path == "/_bulk":
            return httpx.Response(200, json={"errors": False})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    indexer = NewsSearchIndexer(
        elasticsearch_url="http://elasticsearch:9200",
        ollama_url="http://ollama:11434",
        embedding_model="embeddinggemma",
        transport=httpx.MockTransport(handler),
    )

    assert await indexer.index([_article()]) == 1

    mapping = next(request for request in requests if request.method == "PUT")
    assert mapping.url.path == f"/{NEWS_INDEX}"
    assert json.loads(mapping.content)["mappings"]["properties"]["embedding"] == {
        "type": "dense_vector",
        "dims": 3,
        "similarity": "cosine",
    }
    bulk = next(request for request in requests if request.url.path == "/_bulk")
    assert '"_id":"article-1"' in bulk.content.decode()


@pytest.mark.anyio
async def test_search_uses_elasticsearch_rrf_for_keyword_and_vector_retrieval() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
        if request.url.path == f"/{NEWS_INDEX}/_search":
            return httpx.Response(
                200,
                json={"hits": {"hits": [{"_source": {"source_key": "article-1"}}]}},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    indexer = NewsSearchIndexer(
        elasticsearch_url="http://elasticsearch:9200",
        ollama_url="http://ollama:11434",
        embedding_model="embeddinggemma",
        transport=httpx.MockTransport(handler),
    )

    assert await indexer.search("AAPL earnings") == [{"source_key": "article-1"}]

    search = json.loads(requests[-1].content)
    retrievers = search["retriever"]["rrf"]["retrievers"]
    assert retrievers[0]["standard"]["query"]["multi_match"]["query"] == "AAPL earnings"
    assert retrievers[1]["knn"]["field"] == "embedding"
