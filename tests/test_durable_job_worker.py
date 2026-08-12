from contextlib import asynccontextmanager

import pytest

from kis_auto_trading.infrastructure.durable_jobs import worker
from kis_auto_trading.infrastructure.durable_jobs.worker import DurableJobMessageHandler
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage


class FakeSessionRegistry:
    @asynccontextmanager
    async def session(self, target):
        del target
        yield object()


@pytest.mark.anyio
async def test_cancelled_job_message_does_not_run_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDurableJobRepository:
        def __init__(self, session) -> None:
            del session

        async def transition(self, **kwargs) -> bool:
            assert kwargs["expected_status"].value == "requested"
            assert kwargs["status"].value == "running"
            return False

    class UnexpectedHandler:
        async def handle(self, execution) -> None:
            raise AssertionError(f"cancelled job must not run: {execution.job_id}")

    monkeypatch.setattr(worker, "DurableJobRepository", FakeDurableJobRepository)
    message = EventMessage(
        event_type="news.collection.requested",
        aggregate_id="job-1",
        routing_key="news.collection.requested",
        payload={
            "job_id": "job-1",
            "job_type": "news_collection",
            "run_key": "news_collection:2026-08-12T00:00:00+00:00",
            "payload": {"symbols": ["AAPL"]},
        },
    )

    await DurableJobMessageHandler(FakeSessionRegistry(), UnexpectedHandler()).handle(
        message
    )
