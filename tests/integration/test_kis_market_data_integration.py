from __future__ import annotations

import os
import re

import pytest

from kis_auto_trading.infrastructure.kis_market_data import KisMarketDataClient

_READ_ONLY_OPT_IN_ENV = "KIS_READ_ONLY_INTEGRATION"
_STOCK_CODE_ENV = "KIS_INTEGRATION_STOCK_CODE"


@pytest.mark.anyio
async def test_read_only_kis_domestic_stock_price() -> None:
    if os.environ.get(_READ_ONLY_OPT_IN_ENV) != "1":
        pytest.skip(f"set {_READ_ONLY_OPT_IN_ENV}=1 to enable this live read-only check")
    stock_code = os.environ.get(_STOCK_CODE_ENV, "005930")
    if not re.fullmatch(r"[0-9]{6}", stock_code):
        pytest.fail(f"{_STOCK_CODE_ENV} must be a six-digit domestic stock code")

    client = KisMarketDataClient.from_environment()
    try:
        price = await client.get_domestic_stock_price(stock_code)
    finally:
        await client.aclose()

    assert price.stock_code == stock_code
    assert price.current_price
