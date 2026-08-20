from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kis_auto_trading.application.extensions import USER_ROUTERS
from kis_auto_trading.application.signal_subscriptions import (
    list_enabled_signal_subscriptions,
)
from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.modules.signal.generated.models import (
    SignalSubscriptionProjection,
)
from kis_auto_trading.routers.operator_signal import (
    router,
)


def test_operator_signal_route_is_registered_and_token_protected(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERATOR_API_TOKEN", "operator-token")
    assert router in USER_ROUTERS

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get(
            "/internal/operator/signal/subscriptions?stock_code=005930"
        )

    assert response.status_code == 401


def test_operator_signal_route_returns_enabled_projection(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERATOR_API_TOKEN", "operator-token")
    projection = SignalSubscriptionProjection(
        subscription_id=uuid4(),
        user_id=uuid4(),
        shard_id="1",
        stock_code="005930",
        enabled=True,
        revision=2,
    )

    async def fake_list(session_registry, stock_code, *, limit):
        assert session_registry is not None
        assert stock_code == "005930"
        assert limit == 1
        return [projection]

    monkeypatch.setattr(
        "kis_auto_trading.routers.operator_signal.list_enabled_signal_subscriptions",
        fake_list,
    )
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        app.state.session_registry = object()
        response = client.get(
            "/internal/operator/signal/subscriptions?stock_code=005930&limit=1",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 200
    assert response.json() == [projection.model_dump(mode="json")]


class _FakeResult:
    def __init__(self, records):
        self._records = records

    def all(self):
        return self._records


class _FakeSession:
    def __init__(self, records):
        self._records = records

    async def scalars(self, statement):
        assert "signal_subscription_projections" in str(statement)
        assert "stock_code" in str(statement)
        return _FakeResult(self._records)


class _FakeRegistry:
    def __init__(self, session):
        self.session_seen = session
        self.targets = []

    @asynccontextmanager
    async def session(self, target):
        self.targets.append(target)
        yield self.session_seen


@pytest.mark.anyio
async def test_signal_projection_query_uses_global_store_and_enabled_filter() -> None:
    record = type(
        "Record",
        (),
        {
            "subscription_id": uuid4(),
            "user_id": uuid4(),
            "shard_id": "2",
            "stock_code": "005930",
            "enabled": True,
            "revision": 3,
        },
    )()
    registry = _FakeRegistry(_FakeSession([record]))

    result = await list_enabled_signal_subscriptions(
        registry,
        "005930",
        limit=10,
    )

    assert registry.targets == [ShardTarget(store="automation")]
    assert result[0].subscription_id == record.subscription_id
