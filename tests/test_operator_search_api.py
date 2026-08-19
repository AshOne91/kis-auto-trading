from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kis_auto_trading.application.extensions import USER_ROUTERS
from kis_auto_trading.routers.operator_search import (
    get_durable_job_history_search_indexer,
    router,
)


class FakeIndexer:
    async def search(self, query: str, *, limit: int) -> list[dict[str, object]]:
        assert query == "news index"
        assert limit == 1
        return [
            {
                "job_id": "job-1",
                "job_type": "news_index",
                "run_key": "news-index:job-1",
                "status": "succeeded",
                "error_summary": None,
                "result_summary": "articles_indexed",
                "requested_at": datetime(2026, 8, 19, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 19, 1, tzinfo=UTC),
                "payload": {"source_keys": ["must-not-leak"]},
                "embedding": [0.1, 0.2, 0.3],
            }
        ]


def _app(indexer: FakeIndexer) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_durable_job_history_search_indexer] = lambda: indexer
    return app


def test_user_owned_extension_registers_operator_router() -> None:
    assert USER_ROUTERS == (router,)


def test_operator_search_requires_durable_job_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DURABLE_JOB_API_TOKEN", "test-token")

    with TestClient(_app(FakeIndexer())) as client:
        response = client.get("/internal/operator/search/durable-jobs?query=news")

    assert response.status_code == 401


def test_operator_search_returns_safe_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DURABLE_JOB_API_TOKEN", "test-token")

    with TestClient(_app(FakeIndexer())) as client:
        response = client.get(
            "/internal/operator/search/durable-jobs?query=news%20index&limit=1",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    document = response.json()[0]
    assert document["job_id"] == "job-1"
    assert set(document) == {
        "job_id",
        "job_type",
        "run_key",
        "status",
        "error_summary",
        "result_summary",
        "requested_at",
        "updated_at",
    }
