from __future__ import annotations

import pytest

from scripts.verify_kis_read_only_price import stock_code_from_environment


def _environment(**updates: str) -> dict[str, str]:
    environment = {
        "KIS_API_URL": "https://openapi.example",
        "KIS_APP_KEY": "app-key",
        "KIS_APP_SECRET": "app-secret",
        "REDIS_URL": "redis://redis:6379",
    }
    environment.update(updates)
    return environment


def test_stock_code_from_environment_uses_safe_default() -> None:
    assert stock_code_from_environment(_environment()) == "005930"


def test_stock_code_from_environment_rejects_missing_runtime_values() -> None:
    with pytest.raises(ValueError, match="KIS_APP_SECRET"):
        stock_code_from_environment(_environment(KIS_APP_SECRET=""))


def test_stock_code_from_environment_rejects_generated_placeholder() -> None:
    with pytest.raises(ValueError, match="generated placeholder"):
        stock_code_from_environment(_environment(KIS_API_URL="https://example.invalid"))


def test_stock_code_from_environment_rejects_invalid_stock_code() -> None:
    with pytest.raises(ValueError, match="six-digit"):
        stock_code_from_environment(_environment(KIS_INTEGRATION_STOCK_CODE="invalid"))
