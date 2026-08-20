from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kis_auto_trading.application.extensions import USER_ROUTERS
from kis_auto_trading.routers.notifications import router as notifications_router
from kis_auto_trading.routers.operator_market_data import (
    router as market_data_router,
)
from kis_auto_trading.routers.operator_portfolio import (
    router as portfolio_router,
)
from kis_auto_trading.routers.operator_search import (
    get_durable_job_history_search_indexer,
    get_news_search_indexer,
    router,
)
from kis_auto_trading.routers.operator_signal import (
    router as signal_router,
)
from kis_auto_trading.routers.realtime_notifications import (
    router as realtime_notifications_router,
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


class FakeNewsIndexer:
    async def search(self, query: str, *, limit: int) -> list[dict[str, object]]:
        assert query == "AAPL earnings"
        assert limit == 1
        return [
            {
                "source_key": "article-1",
                "source_url": "https://example.test/article-1",
                "provider": "test",
                "title": "AAPL earnings",
                "content": "Apple revenue increased.",
                "symbol": "AAPL",
                "published_at": datetime(2026, 8, 19, tzinfo=UTC),
                "publisher": "test",
                "embedding": [0.1, 0.2, 0.3],
            }
        ]


def _app(indexer: FakeIndexer, news_indexer: FakeNewsIndexer | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_durable_job_history_search_indexer] = lambda: indexer
    if news_indexer is not None:
        app.dependency_overrides[get_news_search_indexer] = lambda: news_indexer
    return app


def test_user_owned_extension_registers_operator_routers() -> None:
    assert USER_ROUTERS == (
        market_data_router,
        portfolio_router,
        router,
        signal_router,
        notifications_router,
        realtime_notifications_router,
    )


def test_operator_search_requires_operator_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_API_TOKEN", "test-token")

    with TestClient(_app(FakeIndexer())) as client:
        response = client.get("/internal/operator/search/durable-jobs?query=news")

    assert response.status_code == 401


def test_operator_search_returns_safe_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DURABLE_JOB_API_TOKEN", "durable-token")
    monkeypatch.setenv("OPERATOR_API_TOKEN", "operator-token")

    with TestClient(_app(FakeIndexer())) as client:
        denied = client.get(
            "/internal/operator/search/durable-jobs?query=news%20index&limit=1",
            headers={"Authorization": "Bearer durable-token"},
        )
        response = client.get(
            "/internal/operator/search/durable-jobs?query=news%20index&limit=1",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert denied.status_code == 401
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


def test_operator_news_search_returns_canonical_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_API_TOKEN", "test-token")

    with TestClient(_app(FakeIndexer(), FakeNewsIndexer())) as client:
        response = client.get(
            "/internal/operator/search/news?query=AAPL%20earnings&limit=1",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    document = response.json()[0]
    assert document["source_key"] == "article-1"
    assert "embedding" not in document
