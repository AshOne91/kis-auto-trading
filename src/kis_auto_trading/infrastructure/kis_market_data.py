from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from kis_auto_trading.infrastructure.distributed_lock import DistributedLock
from kis_auto_trading.infrastructure.external_provider import ExternalProvider
from kis_auto_trading.infrastructure.key_value_store import KeyValueStore
from kis_auto_trading.infrastructure.kis_token_coordinator import (
    KisAccessToken,
    KisTokenCoordinator,
    KisTokenCredentials,
)

_DOMESTIC_STOCK_PRICE_PATH: Final = "/uapi/domestic-stock/v1/quotations/inquire-price"
_DOMESTIC_STOCK_PRICE_TR_ID: Final = "FHKST01010100"
_STOCK_CODE_PATTERN: Final = re.compile(r"[0-9]{6}")


class KisMarketDataError(RuntimeError):
    """Raised when a read-only KIS market-data response is unusable."""


@dataclass(frozen=True, slots=True)
class KisDomesticStockPrice:
    stock_code: str
    current_price: str
    output: Mapping[str, object]


class KisMarketDataClient:
    """Reads KIS domestic stock prices without exposing an order operation."""

    def __init__(
        self,
        provider: ExternalProvider,
        token_coordinator: KisTokenCoordinator,
        credentials: KisTokenCredentials,
    ) -> None:
        self._provider = provider
        self._token_coordinator = token_coordinator
        self._credentials = credentials

    @classmethod
    def from_environment(cls) -> KisMarketDataClient:
        credentials = KisTokenCredentials.from_environment()
        provider = ExternalProvider.from_environment()
        return cls(
            provider,
            KisTokenCoordinator(
                provider,
                DistributedLock.from_environment(),
                KeyValueStore.from_environment(),
                credentials,
            ),
            credentials,
        )

    async def get_domestic_stock_price(
        self, stock_code: str
    ) -> KisDomesticStockPrice:
        if not isinstance(stock_code, str) or not _STOCK_CODE_PATTERN.fullmatch(
            stock_code
        ):
            raise ValueError("stock_code must be a six-digit domestic stock code")
        token = await self._token_coordinator.get_access_token()
        response = await self._provider.request(
            "GET",
            _DOMESTIC_STOCK_PRICE_PATH,
            headers=self._headers(token),
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": stock_code,
            },
            retry_safe=True,
        )
        return self._parse_price_response(
            stock_code,
            response.status_code,
            response.content,
        )

    async def aclose(self) -> None:
        await self._token_coordinator.aclose()

    def _headers(self, token: KisAccessToken) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "accept": "text/plain",
            "charset": "UTF-8",
            "authorization": f"{token.token_type} {token.value}",
            "appkey": self._credentials.app_key,
            "appsecret": self._credentials.app_secret,
            "tr_id": _DOMESTIC_STOCK_PRICE_TR_ID,
            "custtype": "P",
            "tr_cont": "",
        }

    @staticmethod
    def _parse_price_response(
        stock_code: str,
        status_code: int,
        content: bytes,
    ) -> KisDomesticStockPrice:
        if not 200 <= status_code < 300:
            raise KisMarketDataError(
                f"KIS domestic stock price returned HTTP {status_code}"
            )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise KisMarketDataError(
                "KIS domestic stock price response is invalid"
            ) from error
        if not isinstance(payload, Mapping):
            raise KisMarketDataError("KIS domestic stock price response is invalid")
        if payload.get("rt_cd") != "0":
            message = payload.get("msg1", "unknown KIS error")
            raise KisMarketDataError(f"KIS domestic stock price failed: {message}")
        output = payload.get("output")
        if not isinstance(output, Mapping):
            raise KisMarketDataError("KIS domestic stock price response is invalid")
        current_price = output.get("stck_prpr")
        if not isinstance(current_price, str) or not current_price:
            raise KisMarketDataError("KIS domestic stock price response is invalid")
        return KisDomesticStockPrice(
            stock_code=stock_code,
            current_price=current_price,
            output=dict(output),
        )
