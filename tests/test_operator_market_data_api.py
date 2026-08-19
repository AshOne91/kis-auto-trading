from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from kis_auto_trading.application.app_factory import create_app
from kis_auto_trading.infrastructure.kis_market_data import (
    KisDomesticStockPrice,
    KisMarketDataError,
)


@dataclass
class _FakeMarketDataClient:
    result: KisDomesticStockPrice | None = None
    error: Exception | None = None
    requested_stock_codes: list[str] | None = None

    def __post_init__(self) -> None:
        self.requested_stock_codes = []

    async def get_domestic_stock_price(self, stock_code: str) -> KisDomesticStockPrice:
        self.requested_stock_codes.append(stock_code)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


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
        "OPERATOR_API_TOKEN": "operator-token",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_operator_market_data_requires_the_generated_operator_token(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    app = create_app()

    with TestClient(app) as client:
        response = client.get(
            "/internal/operator/market-data/domestic-stock-price?stock_code=005930"
        )

    assert response.status_code == 401


def test_operator_market_data_returns_only_the_current_price(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    app = create_app()
    market_data = _FakeMarketDataClient(
        result=KisDomesticStockPrice(
            stock_code="005930",
            current_price="70000",
            output={"stck_prpr": "70000", "unexposed": "value"},
        )
    )

    with TestClient(app) as client:
        app.state.kis_market_data = market_data
        response = client.get(
            "/internal/operator/market-data/domestic-stock-price?stock_code=005930",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"stock_code": "005930", "current_price": "70000"}
    assert market_data.requested_stock_codes == ["005930"]


def test_operator_market_data_rejects_invalid_stock_codes_before_io(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    app = create_app()
    market_data = _FakeMarketDataClient()

    with TestClient(app) as client:
        app.state.kis_market_data = market_data
        response = client.get(
            "/internal/operator/market-data/domestic-stock-price?stock_code=invalid",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 422
    assert market_data.requested_stock_codes == []


def test_operator_market_data_maps_kis_failures_without_exposing_details(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    app = create_app()
    market_data = _FakeMarketDataClient(error=KisMarketDataError("upstream detail"))

    with TestClient(app) as client:
        app.state.kis_market_data = market_data
        response = client.get(
            "/internal/operator/market-data/domestic-stock-price?stock_code=005930",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "KIS market data is unavailable"}
