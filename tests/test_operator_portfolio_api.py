from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from kis_auto_trading.application.app_factory import create_app
from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisDomesticAccountError,
    KisDomesticStockHolding,
)


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
