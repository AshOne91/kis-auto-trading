from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from kis_auto_trading.application.extensions import USER_ROUTERS
from kis_auto_trading.application.signal_subscriptions import (
    list_enabled_signal_subscriptions,
    list_pending_signal_delivery_intents,
)
from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.modules.signal.generated.models import (
    SignalDeliveryIntent,
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


def test_operator_signal_delivery_intents_returns_pending_records(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERATOR_API_TOKEN", "operator-token")
    intent = SignalDeliveryIntent(
        intent_id=uuid4(),
        signal_id=uuid4(),
        subscription_id=uuid4(),
        user_id=uuid4(),
        shard_id="1",
        stock_code="005930",
        expires_at=datetime.now(UTC),
    )

    async def fake_list(session_registry, stock_code, *, limit):
        assert session_registry is not None
        assert stock_code == "005930"
        assert limit == 1
        return [intent]

    monkeypatch.setattr(
        "kis_auto_trading.routers.operator_signal.list_pending_signal_delivery_intents",
        fake_list,
    )
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        app.state.session_registry = object()
        response = client.get(
            "/internal/operator/signal/delivery-intents?stock_code=005930&limit=1",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 200
    assert response.json() == [intent.model_dump(mode="json")]


def test_operator_signal_delivery_intents_hide_storage_failures(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERATOR_API_TOKEN", "operator-token")

    async def fake_list(session_registry, stock_code, *, limit):
        raise SQLAlchemyError("database detail")

    monkeypatch.setattr(
        "kis_auto_trading.routers.operator_signal.list_pending_signal_delivery_intents",
        fake_list,
    )
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        app.state.session_registry = object()
        response = client.get(
            "/internal/operator/signal/delivery-intents?stock_code=005930",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "signal delivery intent is unavailable"}


class _FakeResult:
    def __init__(self, records):
        self._records = records

    def all(self):
        return self._records


class _FakeSession:
    def __init__(self, records, *, expected_terms):
        self._records = records
        self._expected_terms = expected_terms

    async def scalars(self, statement):
        statement_text = str(statement)
        for term in self._expected_terms:
            assert term in statement_text
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
    registry = _FakeRegistry(
        _FakeSession(
            [record],
            expected_terms=("signal_subscription_projections", "stock_code"),
        )
    )

    result = await list_enabled_signal_subscriptions(
        registry,
        "005930",
        limit=10,
    )

    assert registry.targets == [ShardTarget(store="automation")]
    assert result[0].subscription_id == record.subscription_id


@pytest.mark.anyio
async def test_pending_signal_intent_query_uses_global_store_and_pending_filter() -> None:
    record = type(
        "Record",
        (),
        {
            "intent_id": uuid4(),
            "signal_id": uuid4(),
            "subscription_id": uuid4(),
            "user_id": uuid4(),
            "shard_id": "2",
            "stock_code": "005930",
            "expires_at": datetime.now(UTC),
            "status": "pending",
        },
    )()
    registry = _FakeRegistry(
        _FakeSession(
            [record],
            expected_terms=("signal_delivery_intents", "stock_code", "status"),
        )
    )

    result = await list_pending_signal_delivery_intents(
        registry,
        "005930",
        limit=10,
    )

    assert registry.targets == [ShardTarget(store="automation")]
    assert result[0].intent_id == record.intent_id
    assert result[0].status == "pending"
