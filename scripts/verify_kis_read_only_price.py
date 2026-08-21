from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Mapping

import httpx
from redis.exceptions import RedisError

from kis_auto_trading.infrastructure.kis_market_data import (
    KisMarketDataClient,
    KisMarketDataError,
)
from kis_auto_trading.infrastructure.kis_token_coordinator import (
    KisTokenCoordinatorError,
)

logger = logging.getLogger(__name__)

_REQUIRED_ENVIRONMENT_NAMES = (
    "KIS_API_URL",
    "KIS_APP_KEY",
    "KIS_APP_SECRET",
    "REDIS_URL",
)
_PLACEHOLDER_API_URL = "https://example.invalid"
_STOCK_CODE_PATTERN = re.compile(r"[0-9]{6}")


def stock_code_from_environment(environment: Mapping[str, str]) -> str:
    missing = [name for name in _REQUIRED_ENVIRONMENT_NAMES if not environment.get(name)]
    if missing:
        raise ValueError(f"missing required runtime values: {', '.join(missing)}")
    if environment["KIS_API_URL"] == _PLACEHOLDER_API_URL:
        raise ValueError("KIS_API_URL is still the generated placeholder")
    stock_code = environment.get("KIS_INTEGRATION_STOCK_CODE", "005930")
    if not _STOCK_CODE_PATTERN.fullmatch(stock_code):
        raise ValueError("KIS_INTEGRATION_STOCK_CODE must be a six-digit stock code")
    return stock_code


async def verify_read_only_price() -> None:
    stock_code = stock_code_from_environment(os.environ)
    client = KisMarketDataClient.from_environment()
    try:
        price = await client.get_domestic_stock_price(stock_code)
    finally:
        await client.aclose()
    logger.info("read-only KIS current-price verification succeeded for %s", price.stock_code)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(verify_read_only_price())
    except (
        httpx.HTTPError,
        KisMarketDataError,
        KisTokenCoordinatorError,
        OSError,
        RedisError,
        RuntimeError,
        ValueError,
    ) as error:
        logger.error("read-only KIS current-price verification failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
