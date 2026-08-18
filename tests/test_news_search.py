import json
from datetime import UTC, datetime

import httpx
import pytest

from kis_auto_trading.modules.news.models import NewsArticle
from kis_auto_trading.modules.news.search import (
    NEWS_INDEX,
    NewsSearchIndexer,
    SearchBackend,
)


def _article() -> NewsArticle:
    return NewsArticle(
        source_key="article-1",
        source_url="https://example.test/article-1",
        provider="test",
        title="AAPL earnings rise",
        content="Apple revenue increased after earnings.",
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
    assert (
        '"content":"Apple revenue increased after earnings."' in bulk.content.decode()
    )
    embedding = next(
        request for request in requests if request.url.path == "/api/embed"
    )
    assert json.loads(embedding.content)["input"] == [
        "AAPL earnings rise\nApple revenue increased after earnings.\nAAPL\ntest"
    ]


@pytest.mark.anyio
async def test_index_creates_opensearch_knn_mapping_and_bulk_upserts() -> None:
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
        search_url="http://opensearch:9200",
        search_backend=SearchBackend.OPENSEARCH,
        ollama_url="http://ollama:11434",
        embedding_model="embeddinggemma",
        transport=httpx.MockTransport(handler),
    )

    assert await indexer.index([_article()]) == 1

    mapping = next(request for request in requests if request.method == "PUT")
    payload = json.loads(mapping.content)
    assert payload["settings"] == {"index": {"knn": True}}
    assert payload["mappings"]["properties"]["embedding"] == {
        "type": "knn_vector",
        "dimension": 3,
        "method": {
            "name": "hnsw",
            "engine": "faiss",
            "space_type": "cosinesimil",
        },
    }


@pytest.mark.anyio
async def test_search_fuses_keyword_and_vector_retrieval_without_elasticsearch_rrf() -> (
    None
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
        if request.url.path == f"/{NEWS_INDEX}/_search":
            payload = json.loads(request.content)
            if "query" in payload:
                return httpx.Response(
                    200,
                    json={
                        "hits": {
                            "hits": [
                                {"_source": {"source_key": "article-1"}},
                                {"_source": {"source_key": "article-2"}},
                            ]
                        }
                    },
                )
            if "knn" in payload:
                return httpx.Response(
                    200,
                    json={
                        "hits": {
                            "hits": [
                                {"_source": {"source_key": "article-2"}},
                                {"_source": {"source_key": "article-3"}},
                            ]
                        }
                    },
                )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    indexer = NewsSearchIndexer(
        elasticsearch_url="http://elasticsearch:9200",
        ollama_url="http://ollama:11434",
        embedding_model="embeddinggemma",
        transport=httpx.MockTransport(handler),
    )

    assert await indexer.search("AAPL earnings") == [
        {"source_key": "article-2"},
        {"source_key": "article-1"},
        {"source_key": "article-3"},
    ]

    searches = [
        json.loads(request.content)
        for request in requests
        if request.url.path == f"/{NEWS_INDEX}/_search"
    ]
    keyword_search = next(search for search in searches if "query" in search)
    vector_search = next(search for search in searches if "knn" in search)
    assert keyword_search["query"]["multi_match"]["query"] == "AAPL earnings"
    assert keyword_search["query"]["multi_match"]["fields"] == [
        "title^3",
        "content",
        "symbol^2",
        "publisher",
    ]
    assert vector_search["knn"]["field"] == "embedding"


@pytest.mark.anyio
async def test_search_uses_opensearch_knn_query_and_application_rrf() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
        if request.url.path == f"/{NEWS_INDEX}/_search":
            payload = json.loads(request.content)
            if "knn" in payload.get("query", {}):
                return httpx.Response(
                    200,
                    json={"hits": {"hits": [{"_source": {"source_key": "article-2"}}]}},
                )
            return httpx.Response(
                200,
                json={"hits": {"hits": [{"_source": {"source_key": "article-1"}}]}},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    indexer = NewsSearchIndexer(
        search_url="http://opensearch:9200",
        search_backend=SearchBackend.OPENSEARCH,
        ollama_url="http://ollama:11434",
        embedding_model="embeddinggemma",
        transport=httpx.MockTransport(handler),
    )

    assert await indexer.search("AAPL earnings") == [
        {"source_key": "article-1"},
        {"source_key": "article-2"},
    ]

    vector_search = next(
        json.loads(request.content)
        for request in requests
        if request.url.path == f"/{NEWS_INDEX}/_search"
        and "knn" in json.loads(request.content).get("query", {})
    )
    assert vector_search["query"]["knn"]["embedding"]["vector"] == [0.1, 0.2, 0.3]
