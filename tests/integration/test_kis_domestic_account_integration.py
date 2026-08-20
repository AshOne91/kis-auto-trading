from __future__ import annotations

import os

import pytest

from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisDomesticAccountClient,
    KisDomesticStockHolding,
)

_READ_ONLY_BALANCE_OPT_IN_ENV = "KIS_READ_ONLY_BALANCE_INTEGRATION"


@pytest.mark.anyio
async def test_read_only_kis_domestic_balance() -> None:
    if os.environ.get(_READ_ONLY_BALANCE_OPT_IN_ENV) != "1":
        pytest.skip(
            f"set {_READ_ONLY_BALANCE_OPT_IN_ENV}=1 to enable this live read-only check"
        )

    client = KisDomesticAccountClient.from_environment()
    try:
        holdings = await client.list_domestic_stock_holdings()
    finally:
        await client.aclose()

    assert isinstance(holdings, tuple)
    assert all(isinstance(holding, KisDomesticStockHolding) for holding in holdings)
