from __future__ import annotations

import hashlib
import json
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

_DOMESTIC_BALANCE_PATH: Final = "/uapi/domestic-stock/v1/trading/inquire-balance"
_REAL_BALANCE_TR_ID: Final = "TTTC8434R"
_DEMO_BALANCE_TR_ID: Final = "VTTC8434R"
_MAX_BALANCE_PAGES: Final = 10
_HOLDINGS_CACHE_TTL_SECONDS: Final = 15


class KisAccountConfigurationError(ValueError):
    """Raised when the KIS domestic-account runtime configuration is invalid."""


class KisDomesticAccountError(RuntimeError):
    """Raised when a read-only KIS domestic-account response is unusable."""


@dataclass(frozen=True, slots=True)
class KisAccountCredentials:
    account_number: str
    account_product_code: str
    environment: str

    def __post_init__(self) -> None:
        if not self.account_number.isdecimal() or len(self.account_number) != 8:
            raise KisAccountConfigurationError(
                "KIS account number must be eight decimal digits"
            )
        if (
            not self.account_product_code.isdecimal()
            or len(self.account_product_code) != 2
        ):
            raise KisAccountConfigurationError(
                "KIS account product code must be two decimal digits"
            )
        if self.environment not in {"real", "demo"}:
            raise KisAccountConfigurationError(
                "KIS account environment must be 'real' or 'demo'"
            )

    @classmethod
    def from_environment(cls) -> KisAccountCredentials:
        import os

        values = {
            "KIS_ACCOUNT_NUMBER": os.environ.get("KIS_ACCOUNT_NUMBER"),
            "KIS_ACCOUNT_PRODUCT_CODE": os.environ.get("KIS_ACCOUNT_PRODUCT_CODE"),
            "KIS_ACCOUNT_ENVIRONMENT": os.environ.get("KIS_ACCOUNT_ENVIRONMENT"),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise KisAccountConfigurationError(
                "Missing required KIS environment variables: " + ", ".join(missing)
            )
        return cls(
            account_number=values["KIS_ACCOUNT_NUMBER"],
            account_product_code=values["KIS_ACCOUNT_PRODUCT_CODE"],
            environment=values["KIS_ACCOUNT_ENVIRONMENT"],
        )


@dataclass(frozen=True, slots=True)
class KisDomesticStockHolding:
    stock_code: str
    product_name: str
    holding_quantity: str
    orderable_quantity: str
    current_price: str


class KisDomesticAccountClient:
    """Reads domestic stock holdings without exposing account summaries or orders."""

    def __init__(
        self,
        provider: ExternalProvider,
        token_coordinator: KisTokenCoordinator,
        token_credentials: KisTokenCredentials,
        account_credentials: KisAccountCredentials,
        *,
        holdings_cache: KeyValueStore | None = None,
    ) -> None:
        self._provider = provider
        self._token_coordinator = token_coordinator
        self._token_credentials = token_credentials
        self._account_credentials = account_credentials
        self._holdings_cache = holdings_cache
        identity = (
            f"{account_credentials.environment}:"
            f"{account_credentials.account_number}:"
            f"{account_credentials.account_product_code}"
        ).encode()
        self._holdings_cache_key = (
            "portfolio:domestic-stock-holdings:"
            f"{hashlib.sha256(identity).hexdigest()[:16]}"
        )

    @classmethod
    def from_environment(cls) -> KisDomesticAccountClient:
        token_credentials = KisTokenCredentials.from_environment()
        provider = ExternalProvider.from_environment()
        cache = KeyValueStore.from_environment()
        return cls(
            provider,
            KisTokenCoordinator(
                provider,
                DistributedLock.from_environment(),
                cache,
                token_credentials,
            ),
            token_credentials,
            KisAccountCredentials.from_environment(),
            holdings_cache=cache,
        )

    async def list_domestic_stock_holdings(self) -> tuple[KisDomesticStockHolding, ...]:
        cached = await self._read_cached_holdings()
        if cached is not None:
            return cached
        token = await self._token_coordinator.get_access_token()
        holdings: list[KisDomesticStockHolding] = []
        context_fk = ""
        context_nk = ""
        continuation = ""
        for _ in range(_MAX_BALANCE_PAGES):
            response = await self._provider.request(
                "GET",
                _DOMESTIC_BALANCE_PATH,
                headers=self._headers(token, continuation),
                params=self._params(context_fk, context_nk),
                retry_safe=True,
            )
            payload = self._parse_response(response.status_code, response.content)
            holdings.extend(self._parse_holdings(payload))
            if response.headers.get("tr_cont") not in {"M", "F"}:
                result = tuple(holdings)
                await self._write_cached_holdings(result)
                return result
            context_fk = self._required_string(payload, "ctx_area_fk100")
            context_nk = self._required_string(payload, "ctx_area_nk100")
            continuation = "N"
        raise KisDomesticAccountError("KIS domestic balance pagination limit exceeded")

    async def _read_cached_holdings(
        self,
    ) -> tuple[KisDomesticStockHolding, ...] | None:
        if self._holdings_cache is None:
            return None
        value = await self._holdings_cache.get(self._holdings_cache_key)
        if value is None:
            return None
        try:
            payload = json.loads(value)
            if not isinstance(payload, list):
                return None
            return tuple(
                KisDomesticStockHolding(
                    stock_code=_required_holding_string(item, "stock_code"),
                    product_name=_required_holding_string(item, "product_name"),
                    holding_quantity=_required_holding_string(
                        item, "holding_quantity"
                    ),
                    orderable_quantity=_required_holding_string(
                        item, "orderable_quantity"
                    ),
                    current_price=_required_holding_string(item, "current_price"),
                )
                for item in payload
            )
        except (TypeError, ValueError):
            return None

    async def _write_cached_holdings(
        self, holdings: tuple[KisDomesticStockHolding, ...]
    ) -> None:
        if self._holdings_cache is None:
            return
        await self._holdings_cache.set(
            self._holdings_cache_key,
            json.dumps(
                [
                    {
                        "stock_code": holding.stock_code,
                        "product_name": holding.product_name,
                        "holding_quantity": holding.holding_quantity,
                        "orderable_quantity": holding.orderable_quantity,
                        "current_price": holding.current_price,
                    }
                    for holding in holdings
                ],
                separators=(",", ":"),
            ),
            ttl_seconds=_HOLDINGS_CACHE_TTL_SECONDS,
        )

    async def aclose(self) -> None:
        await self._token_coordinator.aclose()

    def _headers(self, token: KisAccessToken, continuation: str) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "accept": "text/plain",
            "charset": "UTF-8",
            "authorization": f"{token.token_type} {token.value}",
            "appkey": self._token_credentials.app_key,
            "appsecret": self._token_credentials.app_secret,
            "tr_id": (
                _REAL_BALANCE_TR_ID
                if self._account_credentials.environment == "real"
                else _DEMO_BALANCE_TR_ID
            ),
            "custtype": "P",
            "tr_cont": continuation,
        }

    def _params(self, context_fk: str, context_nk: str) -> dict[str, str]:
        return {
            "CANO": self._account_credentials.account_number,
            "ACNT_PRDT_CD": self._account_credentials.account_product_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "01",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": context_fk,
            "CTX_AREA_NK100": context_nk,
        }

    @staticmethod
    def _parse_response(status_code: int, content: bytes) -> Mapping[str, object]:
        if not 200 <= status_code < 300:
            raise KisDomesticAccountError(
                f"KIS domestic balance returned HTTP {status_code}"
            )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise KisDomesticAccountError(
                "KIS domestic balance response is invalid"
            ) from error
        if not isinstance(payload, Mapping):
            raise KisDomesticAccountError("KIS domestic balance response is invalid")
        if payload.get("rt_cd") != "0":
            message = payload.get("msg1", "unknown KIS error")
            raise KisDomesticAccountError(f"KIS domestic balance failed: {message}")
        return payload

    @classmethod
    def _parse_holdings(
        cls, payload: Mapping[str, object]
    ) -> tuple[KisDomesticStockHolding, ...]:
        records = payload.get("output1")
        if not isinstance(records, list):
            raise KisDomesticAccountError("KIS domestic balance response is invalid")
        holdings = []
        for record in records:
            if not isinstance(record, Mapping):
                raise KisDomesticAccountError("KIS domestic balance response is invalid")
            holdings.append(
                KisDomesticStockHolding(
                    stock_code=cls._required_string(record, "pdno"),
                    product_name=cls._required_string(record, "prdt_name"),
                    holding_quantity=cls._required_string(record, "hldg_qty"),
                    orderable_quantity=cls._required_string(record, "ord_psbl_qty"),
                    current_price=cls._required_string(record, "prpr"),
                )
            )
        return tuple(holdings)

    @staticmethod
    def _required_string(payload: Mapping[str, object], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str):
            raise KisDomesticAccountError("KIS domestic balance response is invalid")
        return value


def _required_holding_string(value: object, name: str) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("Cached domestic holdings must be objects")
    field = value.get(name)
    if not isinstance(field, str):
        raise TypeError(f"Cached domestic holding {name} must be a string")
    return field
