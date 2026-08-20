from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kis_auto_trading.routers import durable_jobs


class FakeSessionRegistry:
    def __init__(self) -> None:
        self.targets = []

    @asynccontextmanager
    async def session(self, target):
        self.targets.append(target)
        yield object()


def test_durable_job_api_authenticates_and_reuses_run_key(
    monkeypatch,
) -> None:
    registry = FakeSessionRegistry()
    requests: list[dict[str, object]] = []
    record = SimpleNamespace(
        job_id="job-1",
        job_type="news_collection",
        run_key="news_collection:2026-08-12T00:00:00+00:00",
        status="requested",
        payload={"symbols": ["AAPL"]},
        result={"indexed": 1},
        error=None,
        requested_at=datetime(2026, 8, 12, tzinfo=UTC),
        updated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

    class FakeDurableJobRepository:
        cancel_raced = False

        def __init__(self, session) -> None:
            del session

        async def request(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(job_id="job-1", created=len(requests) == 1)

        async def get(self, job_id: str, **kwargs):
            del kwargs
            return record if job_id == record.job_id else None

        async def list_recent(self, *, job_type: str, limit: int):
            assert job_type == "news_collection"
            assert limit == 5
            return [record]

        async def transition(self, *, expected_status, status, **kwargs):
            del kwargs
            if self.cancel_raced:
                record.status = "cancelled"
                return False
            if record.status != expected_status.value:
                return False
            record.status = status.value
            return True

    monkeypatch.setenv("DURABLE_JOB_API_TOKEN", "test-token")
    monkeypatch.setenv("OPERATOR_API_TOKEN", "operator-token")
    monkeypatch.setattr(durable_jobs, "DurableJobRepository", FakeDurableJobRepository)
    app = FastAPI()
    app.include_router(durable_jobs.router)
    app.dependency_overrides[durable_jobs.get_session_registry] = lambda: registry

    body = {
        "run_key": "news_collection:2026-08-12T00:00:00+00:00",
        "payload": {"symbols": ["AAPL"]},
    }
    market_price_body = {
        "run_key": "market-price:005930",
        "payload": {"stock_code": "005930"},
    }
    with TestClient(app) as client:
        assert client.post("/internal/jobs/news_collection", json=body).status_code == 401
        assert (
            client.post(
                "/internal/jobs/news_collection",
                headers={"Authorization": "Bearer operator-token"},
                json=body,
            ).status_code
            == 401
        )

        created = client.post(
            "/internal/jobs/news_collection",
            headers={"Authorization": "Bearer test-token"},
            json=body,
        )
        repeated = client.post(
            "/internal/jobs/news_collection",
            headers={"Authorization": "Bearer test-token"},
            json=body,
        )
        market_price_created = client.post(
            "/internal/jobs/market_price_snapshot",
            headers={"Authorization": "Bearer test-token"},
            json=market_price_body,
        )
        invalid_market_price = client.post(
            "/internal/jobs/market_price_snapshot",
            headers={"Authorization": "Bearer test-token"},
            json={
                "run_key": "market-price:invalid",
                "payload": {"stock_code": "invalid"},
            },
        )
        history = client.get(
            "/internal/jobs/news_collection?limit=5",
            headers={"Authorization": "Bearer test-token"},
        )
        status = client.get(
            "/internal/jobs/news_collection/job-1",
            headers={"Authorization": "Bearer test-token"},
        )
        cancelled = client.delete(
            "/internal/jobs/news_collection/job-1",
            headers={"Authorization": "Bearer test-token"},
        )
        cancelled_again = client.delete(
            "/internal/jobs/news_collection/job-1",
            headers={"Authorization": "Bearer test-token"},
        )
        status_after_cancel = client.get(
            "/internal/jobs/news_collection/job-1",
            headers={"Authorization": "Bearer test-token"},
        )
        record.status = "requested"
        FakeDurableJobRepository.cancel_raced = True
        raced_cancel = client.delete(
            "/internal/jobs/news_collection/job-1",
            headers={"Authorization": "Bearer test-token"},
        )
        FakeDurableJobRepository.cancel_raced = False
        record.status = "running"
        running_cancel = client.delete(
            "/internal/jobs/news_collection/job-1",
            headers={"Authorization": "Bearer test-token"},
        )

    assert created.status_code == 202
    assert created.json() == {"job_id": "job-1", "created": True}
    assert repeated.status_code == 202
    assert repeated.json() == {"job_id": "job-1", "created": False}
    assert market_price_created.status_code == 202
    assert market_price_created.json() == {"job_id": "job-1", "created": False}
    assert invalid_market_price.status_code == 422
    assert invalid_market_price.json() == {
        "detail": "market_price_snapshot stock_code must be a six-digit domestic stock code"
    }
    assert history.status_code == 200
    assert history.json()[0]["job_id"] == "job-1"
    assert history.json()[0]["status"] == "requested"
    assert requests == [
        {"job_type": "news_collection", **body},
        {"job_type": "news_collection", **body},
        {"job_type": "market_price_snapshot", **market_price_body},
    ]
    assert status.status_code == 200
    assert status.json()["status"] == "requested"
    assert status.json()["result"] == {"indexed": 1}
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled_again.status_code == 200
    assert cancelled_again.json()["status"] == "cancelled"
    assert status_after_cancel.json()["status"] == "cancelled"
    assert raced_cancel.status_code == 200
    assert raced_cancel.json()["status"] == "cancelled"
    assert running_cancel.status_code == 409
    assert [target.store for target in registry.targets] == [
        "automation",
        "automation",
        "automation",
        "automation",
        "automation",
        "automation",
        "automation",
        "automation",
        "automation",
        "automation",
    ]
