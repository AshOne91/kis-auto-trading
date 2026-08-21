from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import ClassVar
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from kis_auto_trading.application import market_price_snapshots
from kis_auto_trading.application.app_factory import create_app
from kis_auto_trading.infrastructure.kis_market_data import (
    KisDomesticDailyCandle,
    KisDomesticStockPrice,
    KisMarketDataError,
)
from kis_auto_trading.modules.market_history import handlers as market_history_handlers


@dataclass
class _FakeMarketDataClient:
    result: KisDomesticStockPrice | None = None
    error: Exception | None = None
    requested_stock_codes: list[str] | None = None
    daily_result: tuple[KisDomesticDailyCandle, ...] = ()
    requested_daily_stock_codes: list[str] | None = None

    def __post_init__(self) -> None:
        self.requested_stock_codes = []
        self.requested_daily_stock_codes = []

    async def get_domestic_stock_price(self, stock_code: str) -> KisDomesticStockPrice:
        self.requested_stock_codes.append(stock_code)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result

    async def get_domestic_daily_candles(
        self, stock_code: str
    ) -> tuple[KisDomesticDailyCandle, ...]:
        self.requested_daily_stock_codes.append(stock_code)
        if self.error is not None:
            raise self.error
        return self.daily_result


class _RecordingSessionRegistry:
    def __init__(self) -> None:
        self.targets = []

    @asynccontextmanager
    async def session(self, target):
        self.targets.append(target)
        yield object()


class _RecordingSnapshotRepository:
    saved: ClassVar[list[object]] = []
    error: ClassVar[Exception | None] = None

    def __init__(self, session: object) -> None:
        del session

    async def save(self, snapshot) -> None:
        if self.error is not None:
            raise self.error
        self.saved.append(snapshot)

    async def find_by_id(self, snapshot_id):
        if self.error is not None:
            raise self.error
        return next(
            (
                snapshot
                for snapshot in self.saved
                if snapshot.snapshot_id == snapshot_id
            ),
            None,
        )


class _RecordingCandleRepository:
    saved: ClassVar[list[object]] = []

    def __init__(self, session: object) -> None:
        del session

    async def save(self, candle) -> None:
        self.saved.append(candle)


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


def test_operator_market_data_persists_a_snapshot_only_through_post(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    _RecordingSnapshotRepository.saved = []
    _RecordingSnapshotRepository.error = None
    monkeypatch.setattr(
        market_price_snapshots,
        "SQLAlchemyMarketPriceSnapshotRepository",
        _RecordingSnapshotRepository,
    )
    app = create_app()
    session_registry = _RecordingSessionRegistry()

    with TestClient(app) as client:
        app.state.kis_market_data = _FakeMarketDataClient(
            result=KisDomesticStockPrice(
                stock_code="005930",
                current_price="70000",
                output={"stck_prpr": "70000"},
            )
        )
        app.state.session_registry = session_registry
        response = client.post(
            "/internal/operator/market-data/domestic-stock-price/snapshots?stock_code=005930",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 200
    assert response.json()["stock_code"] == "005930"
    assert response.json()["current_price"] == "70000"
    assert [target.store for target in session_registry.targets] == ["automation"]
    assert _RecordingSnapshotRepository.saved[0].stock_code == "005930"
    assert _RecordingSnapshotRepository.saved[0].current_price == "70000"


def test_operator_market_data_persists_daily_candles_idempotently(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    _RecordingCandleRepository.saved = []
    monkeypatch.setattr(
        market_history_handlers,
        "SQLAlchemyDomesticDailyCandleRepository",
        _RecordingCandleRepository,
    )
    app = create_app()
    session_registry = _RecordingSessionRegistry()
    market_data = _FakeMarketDataClient(
        daily_result=(
            KisDomesticDailyCandle(
                stock_code="005930",
                trading_date="20260821",
                open_price="70000",
                high_price="71000",
                low_price="69000",
                close_price="70500",
                volume=123456,
            ),
        )
    )

    with TestClient(app) as client:
        app.state.kis_market_data = market_data
        app.state.session_registry = session_registry
        first = client.post(
            "/internal/operator/market-data/domestic-daily-candles?stock_code=005930",
            headers={"Authorization": "Bearer operator-token"},
        )
        second = client.post(
            "/internal/operator/market-data/domestic-daily-candles?stock_code=005930",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()[0]["trading_date"] == "20260821"
    assert first.json()[0]["volume"] == 123456
    assert market_data.requested_daily_stock_codes == ["005930", "005930"]
    assert [target.store for target in session_registry.targets] == [
        "automation",
        "automation",
    ]
    assert _RecordingCandleRepository.saved[0].candle_id == (
        _RecordingCandleRepository.saved[1].candle_id
    )


def test_operator_market_data_reads_a_snapshot_by_id(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    _RecordingSnapshotRepository.saved = []
    _RecordingSnapshotRepository.error = None
    monkeypatch.setattr(
        market_price_snapshots,
        "SQLAlchemyMarketPriceSnapshotRepository",
        _RecordingSnapshotRepository,
    )
    app = create_app()
    session_registry = _RecordingSessionRegistry()

    with TestClient(app) as client:
        app.state.kis_market_data = _FakeMarketDataClient(
            result=KisDomesticStockPrice(
                stock_code="005930",
                current_price="70000",
                output={"stck_prpr": "70000"},
            )
        )
        app.state.session_registry = session_registry
        created = client.post(
            "/internal/operator/market-data/domestic-stock-price/snapshots?stock_code=005930",
            headers={"Authorization": "Bearer operator-token"},
        )
        response = client.get(
            f"/internal/operator/market-data/domestic-stock-price/snapshots/{created.json()['snapshot_id']}",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert created.status_code == 200
    assert response.status_code == 200
    assert response.json() == created.json()
    assert [target.store for target in session_registry.targets] == [
        "automation",
        "automation",
    ]


def test_operator_market_data_returns_not_found_for_unknown_snapshot(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    _RecordingSnapshotRepository.saved = []
    _RecordingSnapshotRepository.error = None
    monkeypatch.setattr(
        market_price_snapshots,
        "SQLAlchemyMarketPriceSnapshotRepository",
        _RecordingSnapshotRepository,
    )
    app = create_app()

    with TestClient(app) as client:
        app.state.session_registry = _RecordingSessionRegistry()
        response = client.get(
            f"/internal/operator/market-data/domestic-stock-price/snapshots/{uuid4()}",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Market price snapshot was not found"}


def test_operator_market_data_hides_snapshot_lookup_failures(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    _RecordingSnapshotRepository.saved = []
    _RecordingSnapshotRepository.error = SQLAlchemyError("database detail")
    monkeypatch.setattr(
        market_price_snapshots,
        "SQLAlchemyMarketPriceSnapshotRepository",
        _RecordingSnapshotRepository,
    )
    app = create_app()

    with TestClient(app) as client:
        app.state.session_registry = _RecordingSessionRegistry()
        response = client.get(
            f"/internal/operator/market-data/domestic-stock-price/snapshots/{uuid4()}",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "KIS market data persistence is unavailable"}


def test_operator_market_data_hides_snapshot_persistence_failures(monkeypatch) -> None:
    _configure_environment(monkeypatch)
    _RecordingSnapshotRepository.saved = []
    _RecordingSnapshotRepository.error = SQLAlchemyError("database detail")
    monkeypatch.setattr(
        market_price_snapshots,
        "SQLAlchemyMarketPriceSnapshotRepository",
        _RecordingSnapshotRepository,
    )
    app = create_app()

    with TestClient(app) as client:
        app.state.kis_market_data = _FakeMarketDataClient(
            result=KisDomesticStockPrice(
                stock_code="005930",
                current_price="70000",
                output={"stck_prpr": "70000"},
            )
        )
        app.state.session_registry = _RecordingSessionRegistry()
        response = client.post(
            "/internal/operator/market-data/domestic-stock-price/snapshots?stock_code=005930",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "KIS market data persistence is unavailable"}
