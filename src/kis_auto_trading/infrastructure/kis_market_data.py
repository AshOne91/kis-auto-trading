from __future__ import annotations

import hashlib
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
_DOMESTIC_DAILY_PRICE_PATH: Final = (
    "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
)
_DOMESTIC_DAILY_PRICE_TR_ID: Final = "FHKST01010400"
_STOCK_CODE_PATTERN: Final = re.compile(r"[0-9]{6}")
_PRICE_CACHE_TTL_SECONDS: Final = 2
_DAILY_PRICE_CACHE_TTL_SECONDS: Final = 300


class KisMarketDataError(RuntimeError):
    """Raised when a read-only KIS market-data response is unusable."""


@dataclass(frozen=True, slots=True)
class KisDomesticStockPrice:
    stock_code: str
    current_price: str
    output: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class KisDomesticDailyCandle:
    stock_code: str
    trading_date: str
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    volume: int


class KisMarketDataClient:
    """Reads KIS domestic market data without exposing an order operation."""

    def __init__(
        self,
        provider: ExternalProvider,
        token_coordinator: KisTokenCoordinator,
        credentials: KisTokenCredentials,
        *,
        price_cache: KeyValueStore | None = None,
    ) -> None:
        self._provider = provider
        self._token_coordinator = token_coordinator
        self._credentials = credentials
        self._price_cache = price_cache

    @classmethod
    def from_environment(cls) -> KisMarketDataClient:
        credentials = KisTokenCredentials.from_environment()
        provider = ExternalProvider.from_environment()
        cache = KeyValueStore.from_environment()
        return cls(
            provider,
            KisTokenCoordinator(
                provider,
                DistributedLock.from_environment(),
                cache,
                credentials,
            ),
            credentials,
            price_cache=cache,
        )

    async def get_domestic_stock_price(
        self, stock_code: str
    ) -> KisDomesticStockPrice:
        if not isinstance(stock_code, str) or not _STOCK_CODE_PATTERN.fullmatch(
            stock_code
        ):
            raise ValueError("stock_code must be a six-digit domestic stock code")
        cached = await self._read_cached_price(stock_code)
        if cached is not None:
            return cached
        token = await self._token_coordinator.get_access_token()
        response = await self._provider.request(
            "GET",
            _DOMESTIC_STOCK_PRICE_PATH,
            headers=self._headers(token, _DOMESTIC_STOCK_PRICE_TR_ID),
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": stock_code,
            },
            retry_safe=True,
        )
        price = self._parse_price_response(
            stock_code,
            response.status_code,
            response.content,
        )
        await self._write_cached_price(price)
        return price

    async def get_domestic_daily_candles(
        self, stock_code: str
    ) -> tuple[KisDomesticDailyCandle, ...]:
        if not isinstance(stock_code, str) or not _STOCK_CODE_PATTERN.fullmatch(
            stock_code
        ):
            raise ValueError("stock_code must be a six-digit domestic stock code")
        cached = await self._read_cached_daily_candles(stock_code)
        if cached is not None:
            return cached
        token = await self._token_coordinator.get_access_token()
        response = await self._provider.request(
            "GET",
            _DOMESTIC_DAILY_PRICE_PATH,
            headers=self._headers(token, _DOMESTIC_DAILY_PRICE_TR_ID),
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": stock_code,
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",
            },
            retry_safe=True,
        )
        candles = self._parse_daily_price_response(
            stock_code,
            response.status_code,
            response.content,
        )
        await self._write_cached_daily_candles(stock_code, candles)
        return candles

    def _cache_key(self, stock_code: str) -> str:
        identity = f"{self._credentials.scope}:{self._credentials.app_key}".encode()
        suffix = hashlib.sha256(identity).hexdigest()[:16]
        return f"market:domestic-price:{suffix}:{stock_code}"

    def _daily_cache_key(self, stock_code: str) -> str:
        identity = f"{self._credentials.scope}:{self._credentials.app_key}".encode()
        suffix = hashlib.sha256(identity).hexdigest()[:16]
        return f"market:domestic-daily:{suffix}:{stock_code}"

    async def _read_cached_price(
        self, stock_code: str
    ) -> KisDomesticStockPrice | None:
        if self._price_cache is None:
            return None
        value = await self._price_cache.get(self._cache_key(stock_code))
        if value is None:
            return None
        try:
            payload = json.loads(value)
            if not isinstance(payload, Mapping):
                return None
            output = payload.get("output")
            current_price = payload.get("current_price")
            if not isinstance(output, Mapping) or not isinstance(current_price, str):
                return None
            return KisDomesticStockPrice(
                stock_code=stock_code,
                current_price=current_price,
                output=dict(output),
            )
        except (TypeError, ValueError):
            return None

    async def _write_cached_price(self, price: KisDomesticStockPrice) -> None:
        if self._price_cache is None:
            return
        await self._price_cache.set(
            self._cache_key(price.stock_code),
            json.dumps(
                {
                    "current_price": price.current_price,
                    "output": dict(price.output),
                },
                separators=(",", ":"),
            ),
            ttl_seconds=_PRICE_CACHE_TTL_SECONDS,
        )

    async def _read_cached_daily_candles(
        self, stock_code: str
    ) -> tuple[KisDomesticDailyCandle, ...] | None:
        if self._price_cache is None:
            return None
        value = await self._price_cache.get(self._daily_cache_key(stock_code))
        if value is None:
            return None
        try:
            payload = json.loads(value)
            if not isinstance(payload, list):
                return None
            return self._parse_daily_price_response(
                stock_code,
                200,
                json.dumps({"rt_cd": "0", "output": payload}).encode(),
            )
        except (KisMarketDataError, TypeError, ValueError):
            return None

    async def _write_cached_daily_candles(
        self,
        stock_code: str,
        candles: tuple[KisDomesticDailyCandle, ...],
    ) -> None:
        if self._price_cache is None:
            return
        await self._price_cache.set(
            self._daily_cache_key(stock_code),
            json.dumps(
                [
                    {
                        "stck_bsop_date": candle.trading_date,
                        "stck_oprc": candle.open_price,
                        "stck_hgpr": candle.high_price,
                        "stck_lwpr": candle.low_price,
                        "stck_clpr": candle.close_price,
                        "acml_vol": str(candle.volume),
                    }
                    for candle in candles
                ],
                separators=(",", ":"),
            ),
            ttl_seconds=_DAILY_PRICE_CACHE_TTL_SECONDS,
        )

    async def aclose(self) -> None:
        await self._token_coordinator.aclose()

    def _headers(self, token: KisAccessToken, tr_id: str) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "accept": "text/plain",
            "charset": "UTF-8",
            "authorization": f"{token.token_type} {token.value}",
            "appkey": self._credentials.app_key,
            "appsecret": self._credentials.app_secret,
            "tr_id": tr_id,
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

    @staticmethod
    def _parse_daily_price_response(
        stock_code: str,
        status_code: int,
        content: bytes,
    ) -> tuple[KisDomesticDailyCandle, ...]:
        if not 200 <= status_code < 300:
            raise KisMarketDataError(
                f"KIS domestic daily price returned HTTP {status_code}"
            )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise KisMarketDataError(
                "KIS domestic daily price response is invalid"
            ) from error
        if not isinstance(payload, Mapping) or payload.get("rt_cd") != "0":
            raise KisMarketDataError("KIS domestic daily price response is invalid")
        output = payload.get("output")
        if not isinstance(output, list):
            raise KisMarketDataError("KIS domestic daily price response is invalid")

        candles: list[KisDomesticDailyCandle] = []
        for item in output:
            if not isinstance(item, Mapping):
                raise KisMarketDataError("KIS domestic daily price response is invalid")
            values = (
                item.get("stck_bsop_date"),
                item.get("stck_oprc"),
                item.get("stck_hgpr"),
                item.get("stck_lwpr"),
                item.get("stck_clpr"),
                item.get("acml_vol"),
            )
            if not all(isinstance(value, str) and value for value in values):
                raise KisMarketDataError("KIS domestic daily price response is invalid")
            trading_date, open_price, high_price, low_price, close_price, volume = values
            if len(trading_date) != 8 or not trading_date.isdigit() or not volume.isdigit():
                raise KisMarketDataError("KIS domestic daily price response is invalid")
            candles.append(
                KisDomesticDailyCandle(
                    stock_code=stock_code,
                    trading_date=trading_date,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=int(volume),
                )
            )
        return tuple(candles)
