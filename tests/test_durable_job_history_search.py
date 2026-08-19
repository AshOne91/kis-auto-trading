import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from kis_auto_trading.modules.operations.durable_job_history_search import (
    JOB_HISTORY_INDEX,
    DurableJobHistorySearchIndexer,
)


def _record() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        job_type="news_collection",
        run_key="news:yahoo:2026-08-19T00:00:00Z",
        status="failed",
        payload={"symbols": ["PRIVATE_PAYLOAD_VALUE"]},
        result={"articles_collected": 2, "symbols": ["AAPL"]},
        error="provider timed out while collecting news",
        requested_at=datetime(2026, 8, 19, tzinfo=UTC),
        updated_at=datetime(2026, 8, 19, 1, tzinfo=UTC),
    )


def _indexer(transport: httpx.AsyncBaseTransport) -> DurableJobHistorySearchIndexer:
    return DurableJobHistorySearchIndexer(
        search_url="http://search.test",
        ollama_url="http://ollama.test",
        embedding_model="embedding-test",
        transport=transport,
    )


@pytest.mark.anyio
async def test_index_uses_safe_job_projection_and_hybrid_mapping() -> None:
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

    assert await _indexer(httpx.MockTransport(handler)).index([_record()]) == 1

    mapping = next(request for request in requests if request.method == "PUT")
    assert mapping.url.path == f"/{JOB_HISTORY_INDEX}"
    assert json.loads(mapping.content)["mappings"]["properties"]["embedding"] == {
        "type": "dense_vector",
        "dims": 3,
        "similarity": "cosine",
    }
    bulk = next(request for request in requests if request.url.path == "/_bulk")
    document = json.loads(bulk.content.decode().splitlines()[1])
    assert document["job_id"] == "job-1"
    assert document["result_summary"] == "articles_collected, symbols"
    assert "payload" not in document
    assert "PRIVATE_PAYLOAD_VALUE" not in bulk.content.decode()
    assert "AAPL" not in bulk.content.decode()


@pytest.mark.anyio
async def test_search_ranks_operator_failure_for_hybrid_query() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
        if request.url.path == f"/{JOB_HISTORY_INDEX}/_search":
            payload = json.loads(request.content)
            if "query" in payload:
                return httpx.Response(
                    200,
                    json={
                        "hits": {
                            "hits": [
                                {"_source": {"job_id": "job-1", "status": "failed"}},
                                {"_source": {"job_id": "job-2", "status": "succeeded"}},
                            ]
                        }
                    },
                )
            return httpx.Response(
                200,
                json={
                    "hits": {
                        "hits": [{"_source": {"job_id": "job-1", "status": "failed"}}]
                    }
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    assert await _indexer(httpx.MockTransport(handler)).search(
        "news collection failed"
    ) == [
        {"job_id": "job-1", "status": "failed"},
        {"job_id": "job-2", "status": "succeeded"},
    ]

    keyword_search = next(
        json.loads(request.content)
        for request in requests
        if request.url.path == f"/{JOB_HISTORY_INDEX}/_search"
        and "query" in json.loads(request.content)
    )
    assert keyword_search["query"]["multi_match"]["fields"] == [
        "job_type^3",
        "run_key^2",
        "status^2",
        "error_summary",
        "result_summary",
    ]
