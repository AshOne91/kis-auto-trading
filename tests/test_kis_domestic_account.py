from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from kis_auto_trading.infrastructure.distributed_lock import (
    DistributedLock,
    FakeDistributedLockClient,
)
from kis_auto_trading.infrastructure.external_provider import (
    ExternalProvider,
    ExternalResponse,
)
from kis_auto_trading.infrastructure.key_value_store import (
    FakeKeyValueStoreClient,
    KeyValueStore,
)
from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisAccountConfigurationError,
    KisAccountCredentials,
    KisDomesticAccountClient,
    KisDomesticAccountError,
)
from kis_auto_trading.infrastructure.kis_token_coordinator import (
    KisTokenCoordinator,
    KisTokenCredentials,
)


@dataclass(frozen=True, slots=True)
class _Request:
    method: str
    path: str
    headers: Mapping[str, str] | None
    params: Mapping[str, str] | None
    retry_safe: bool | None


class _CapturingProviderClient:
    def __init__(self, responses: list[ExternalResponse]) -> None:
        self._responses = deque(responses)
        self.requests: list[_Request] = []

    async def health_check(self) -> None:
        return None

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        json: object | None = None,
        content: bytes | None = None,
        retry_safe: bool | None = None,
    ) -> ExternalResponse:
        del json, content
        self.requests.append(
            _Request(method, path, dict(headers) if headers else None, params, retry_safe)
        )
        return self._responses.popleft()

    async def aclose(self) -> None:
        return None


def _client(
    responses: list[ExternalResponse],
    *,
    environment: str = "real",
    cache: KeyValueStore | None = None,
) -> tuple[KisDomesticAccountClient, _CapturingProviderClient]:
    transport = _CapturingProviderClient(responses)
    provider = ExternalProvider(transport)
    token_credentials = KisTokenCredentials("test-app-key", "test-app-secret")
    cache = cache or KeyValueStore(FakeKeyValueStoreClient(3600), 3600)
    coordinator = KisTokenCoordinator(
        provider,
        DistributedLock(FakeDistributedLockClient(30), 30),
        cache,
        token_credentials,
    )
    return (
        KisDomesticAccountClient(
            provider,
            coordinator,
            token_credentials,
            KisAccountCredentials("12345678", "01", environment),
            holdings_cache=cache,
        ),
        transport,
    )


def _token_response() -> ExternalResponse:
    return ExternalResponse(
        status_code=200,
        headers={},
        content=(
            b'{"access_token":"token-value","token_type":"Bearer",'
            b'"expires_in":3600}'
        ),
    )


@pytest.mark.anyio
async def test_domestic_balance_uses_official_request_shape_and_paginates() -> None:
    client, transport = _client(
        [
            _token_response(),
            ExternalResponse(
                status_code=200,
                headers={"tr_cont": "M"},
                content=(
                    b'{"rt_cd":"0","output1":[{"pdno":"005930",'
                    b'"prdt_name":"Samsung","hldg_qty":"10",'
                    b'"ord_psbl_qty":"8","prpr":"70000"}],'
                    b'"ctx_area_fk100":"next-fk","ctx_area_nk100":"next-nk"}'
                ),
            ),
            ExternalResponse(
                status_code=200,
                headers={"tr_cont": "D"},
                content=(
                    b'{"rt_cd":"0","output1":[{"pdno":"000660",'
                    b'"prdt_name":"SK hynix","hldg_qty":"5",'
                    b'"ord_psbl_qty":"5","prpr":"200000"}]}'
                ),
            ),
        ]
    )

    holdings = await client.list_domestic_stock_holdings()

    assert [holding.stock_code for holding in holdings] == ["005930", "000660"]
    assert [(request.method, request.path) for request in transport.requests] == [
        ("POST", "/oauth2/tokenP"),
        ("GET", "/uapi/domestic-stock/v1/trading/inquire-balance"),
        ("GET", "/uapi/domestic-stock/v1/trading/inquire-balance"),
    ]
    assert transport.requests[1].headers == {
        "content-type": "application/json",
        "accept": "text/plain",
        "charset": "UTF-8",
        "authorization": "Bearer token-value",
        "appkey": "test-app-key",
        "appsecret": "test-app-secret",
        "tr_id": "TTTC8434R",
        "custtype": "P",
        "tr_cont": "",
    }
    assert transport.requests[1].params == {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "",
        "INQR_DVSN": "01",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }
    assert transport.requests[2].headers["tr_cont"] == "N"
    assert transport.requests[2].params["CTX_AREA_FK100"] == "next-fk"
    assert transport.requests[2].params["CTX_AREA_NK100"] == "next-nk"
    assert transport.requests[1].retry_safe is True


@pytest.mark.anyio
async def test_domestic_balance_rejects_error_envelopes() -> None:
    client, _ = _client(
        [
            _token_response(),
            ExternalResponse(
                status_code=200,
                headers={},
                content=b'{"rt_cd":"1","msg1":"account unavailable"}',
            ),
        ]
    )

    with pytest.raises(KisDomesticAccountError, match="account unavailable"):
        await client.list_domestic_stock_holdings()


@pytest.mark.anyio
async def test_domestic_balance_caches_one_read_only_result() -> None:
    client, transport = _client(
        [
            _token_response(),
            ExternalResponse(
                status_code=200,
                headers={"tr_cont": "D"},
                content=(
                    b'{"rt_cd":"0","output1":[{"pdno":"005930",'
                    b'"prdt_name":"Samsung","hldg_qty":"10",'
                    b'"ord_psbl_qty":"8","prpr":"70000"}]}'
                ),
            ),
        ]
    )

    first = await client.list_domestic_stock_holdings()
    second = await client.list_domestic_stock_holdings()

    assert second == first
    assert [(request.method, request.path) for request in transport.requests] == [
        ("POST", "/oauth2/tokenP"),
        ("GET", "/uapi/domestic-stock/v1/trading/inquire-balance"),
    ]


@pytest.mark.anyio
async def test_domestic_balance_ignores_a_malformed_cache_value() -> None:
    cache = KeyValueStore(FakeKeyValueStoreClient(3600), 3600)
    client, transport = _client(
        [
            _token_response(),
            ExternalResponse(
                status_code=200,
                headers={"tr_cont": "D"},
                content=(
                    b'{"rt_cd":"0","output1":[{"pdno":"005930",'
                    b'"prdt_name":"Samsung","hldg_qty":"10",'
                    b'"ord_psbl_qty":"8","prpr":"70000"}]}'
                ),
            ),
        ],
        cache=cache,
    )
    await cache.set(client._holdings_cache_key, "not-json", ttl_seconds=15)

    holdings = await client.list_domestic_stock_holdings()

    assert [holding.stock_code for holding in holdings] == ["005930"]
    assert [(request.method, request.path) for request in transport.requests] == [
        ("POST", "/oauth2/tokenP"),
        ("GET", "/uapi/domestic-stock/v1/trading/inquire-balance"),
    ]


def test_domestic_balance_rejects_invalid_account_configuration_before_io() -> None:
    with pytest.raises(KisAccountConfigurationError, match="eight decimal"):
        KisAccountCredentials("not-an-account", "01", "real")
    with pytest.raises(KisAccountConfigurationError, match="'real' or 'demo'"):
        KisAccountCredentials("12345678", "01", "unknown")
