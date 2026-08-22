from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from kis_auto_trading.application.app_factory import create_app
from kis_auto_trading.infrastructure.database.provider import get_session_registry
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisDomesticAccountError,
    KisDomesticStockHolding,
)
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.infrastructure.session_store.provider import get_current_session
from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)
from kis_auto_trading.modules.portfolio.generated.models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)
from kis_auto_trading.modules.portfolio.handlers import PortfolioSnapshotCapture
from kis_auto_trading.routers import operator_portfolio


@dataclass
class _FakeDomesticAccountClient:
    holdings: tuple[KisDomesticStockHolding, ...] = ()
    error: Exception | None = None
    requests: int = 0

    async def list_domestic_stock_holdings(self) -> tuple[KisDomesticStockHolding, ...]:
        self.requests += 1
        if self.error is not None:
            raise self.error
        return self.holdings


def _configure_environment(monkeypatch) -> None:
    values = {
        "REDIS_URL": "redis://localhost:6379/0",
        "IDENTITY_DATABASE_URL": "postgresql+asyncpg://user:password@localhost/database",
        "AUTOMATION_DATABASE_URL": "postgresql+asyncpg://user:password@localhost/database",
        "ACCOUNT_SHARD_1_DATABASE_URL": "postgresql+asyncpg://user:password@localhost/database",
        "ACCOUNT_SHARD_2_DATABASE_URL": "postgresql+asyncpg://user:password@localhost/database",
        "KIS_API_URL": "https://example.invalid",
        "KIS_APP_KEY": "test-app-key",
        "KIS_APP_SECRET": "test-app-secret",
        "KIS_ACCOUNT_NUMBER": "12345678",
        "KIS_ACCOUNT_PRODUCT_CODE": "01",
        "KIS_ACCOUNT_ENVIRONMENT": "demo",
        "OPERATOR_API_TOKEN": "operator-token",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _session(access_level: str = "user") -> SessionData:
    return SessionData(
        session_id="session-id",
        user_id="00000000-0000-0000-0000-000000000001",
        data={"shard_id": "1", "access_level": access_level},
    )


def _connection(
    *, provider: str = "kis", credential_ref: str = "kis:default", status: str = "active"
) -> BrokerageAccountConnection:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    return BrokerageAccountConnection(
        connection_id=UUID("00000000-0000-0000-0000-000000000002"),
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        provider=provider,
        environment="demo",
        display_name="KIS default account",
        account_mask="****5678",
        credential_ref=credential_ref,
        status=status,
        created_at=now,
        updated_at=now,
    )


def _user_app(account: _FakeDomesticAccountClient) -> FastAPI:
    app = FastAPI()
    app.include_router(operator_portfolio.user_router)
    app.include_router(operator_portfolio.portfolio_router)
    app.state.kis_domestic_account = account
    app.dependency_overrides[get_current_session] = _session
    app.dependency_overrides[get_session_registry] = lambda: cast(
        AsyncSessionRegistry, object()
    )
    return app


def test_operator_portfolio_requires_the_generated_operator_token(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/internal/operator/portfolio/domestic-stock-holdings")

    assert response.status_code == 401


def test_operator_portfolio_returns_only_typed_holdings(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    app = create_app()
    account = _FakeDomesticAccountClient(
        holdings=(
            KisDomesticStockHolding(
                stock_code="005930",
                product_name="Samsung",
                holding_quantity="10",
                orderable_quantity="8",
                current_price="70000",
            ),
        )
    )

    with TestClient(app) as client:
        app.state.kis_domestic_account = account
        response = client.get(
            "/internal/operator/portfolio/domestic-stock-holdings",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "stock_code": "005930",
            "product_name": "Samsung",
            "holding_quantity": "10",
            "orderable_quantity": "8",
            "current_price": "70000",
        }
    ]
    assert account.requests == 1


def test_operator_portfolio_hides_kis_failures(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    app = create_app()
    account = _FakeDomesticAccountClient(error=KisDomesticAccountError("detail"))

    with TestClient(app) as client:
        app.state.kis_domestic_account = account
        response = client.get(
            "/internal/operator/portfolio/domestic-stock-holdings",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "KIS domestic account is unavailable"}


def test_user_portfolio_reads_holdings_only_after_connection_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = _FakeDomesticAccountClient(
        holdings=(
            KisDomesticStockHolding(
                stock_code="005930",
                product_name="Samsung",
                holding_quantity="10",
                orderable_quantity="8",
                current_price="70000",
            ),
        )
    )

    async def fake_get_connection(*_args) -> BrokerageAccountConnection:
        return _connection()

    monkeypatch.setattr(
        operator_portfolio.handlers, "get_connection", fake_get_connection
    )
    with TestClient(_user_app(account)) as client:
        response = client.get(
            "/api/brokerage-account/domestic-stock-holdings"
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "stock_code": "005930",
            "product_name": "Samsung",
            "holding_quantity": "10",
            "orderable_quantity": "8",
            "current_price": "70000",
        }
    ]
    assert account.requests == 1


@pytest.mark.parametrize(
    ("connection", "status_code"),
    [
        (_connection(provider="other"), 409),
        (_connection(credential_ref="kis:unknown"), 409),
        (_connection(status="inactive"), 409),
    ],
)
def test_user_portfolio_rejects_unavailable_connections_before_kis_io(
    monkeypatch: pytest.MonkeyPatch,
    connection: BrokerageAccountConnection,
    status_code: int,
) -> None:
    account = _FakeDomesticAccountClient()

    async def fake_get_connection(*_args) -> BrokerageAccountConnection:
        return connection

    monkeypatch.setattr(
        operator_portfolio.handlers, "get_connection", fake_get_connection
    )
    with TestClient(_user_app(account)) as client:
        response = client.get(
            "/api/brokerage-account/domestic-stock-holdings"
        )

    assert response.status_code == status_code
    assert account.requests == 0


@pytest.mark.parametrize("status_code", [403, 404])
def test_user_portfolio_propagates_connection_denial_before_kis_io(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    account = _FakeDomesticAccountClient()

    async def fake_get_connection(*_args) -> BrokerageAccountConnection:
        raise HTTPException(status_code=status_code, detail="denied")

    monkeypatch.setattr(
        operator_portfolio.handlers, "get_connection", fake_get_connection
    )
    with TestClient(_user_app(account)) as client:
        response = client.get(
            "/api/brokerage-account/domestic-stock-holdings"
        )

    assert response.status_code == status_code
    assert account.requests == 0


def test_user_portfolio_capture_requires_a_key_and_returns_the_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = _FakeDomesticAccountClient()
    connection = _connection()
    captured_at = datetime(2026, 8, 22, tzinfo=UTC)
    snapshot = PortfolioSnapshot(
        snapshot_id=UUID("00000000-0000-0000-0000-000000000003"),
        connection_id=connection.connection_id,
        user_id=connection.user_id,
        captured_at=captured_at,
        position_count=1,
    )
    position = PortfolioPositionSnapshot(
        position_id=UUID("00000000-0000-0000-0000-000000000004"),
        snapshot_id=snapshot.snapshot_id,
        user_id=connection.user_id,
        stock_code="005930",
        product_name="Samsung",
        holding_quantity="10",
        orderable_quantity="8",
        current_price="70000",
    )
    keys: list[str] = []

    async def fake_get_connection(*_args) -> BrokerageAccountConnection:
        return connection

    async def fake_capture(
        _session_data,
        _registry,
        received_connection,
        received_account,
        idempotency_key,
    ) -> PortfolioSnapshotCapture:
        assert received_connection == connection
        assert received_account is account
        keys.append(idempotency_key)
        return PortfolioSnapshotCapture(snapshot=snapshot, positions=(position,))

    async def fake_get_snapshot(*_args) -> PortfolioSnapshotCapture:
        return PortfolioSnapshotCapture(snapshot=snapshot, positions=(position,))

    monkeypatch.setattr(
        operator_portfolio.handlers, "get_connection", fake_get_connection
    )
    monkeypatch.setattr(
        operator_portfolio.portfolio_handlers,
        "capture_portfolio_snapshot",
        fake_capture,
    )
    monkeypatch.setattr(
        operator_portfolio.portfolio_handlers,
        "get_portfolio_snapshot",
        fake_get_snapshot,
    )
    with TestClient(_user_app(account)) as client:
        missing_key = client.post(
            "/api/portfolio/snapshots"
        )
        long_key = client.post(
            "/api/portfolio/snapshots",
            headers={"Idempotency-Key": "x" * 129},
        )
        response = client.post(
            "/api/portfolio/snapshots",
            headers={"Idempotency-Key": "daily-close"},
        )
        loaded = client.get(f"/api/portfolio/snapshots/{snapshot.snapshot_id}")

    assert missing_key.status_code == 400
    assert long_key.status_code == 400
    assert response.status_code == 200
    assert response.json() == {
        "snapshot": snapshot.model_dump(mode="json"),
        "positions": [position.model_dump(mode="json")],
    }
    assert loaded.status_code == 200
    assert loaded.json() == response.json()
    assert keys == ["daily-close"]
    assert account.requests == 0
