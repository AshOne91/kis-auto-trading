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
from kis_auto_trading.infrastructure.kis_market_data import (
    KisMarketDataClient,
    KisMarketDataError,
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
) -> tuple[KisMarketDataClient, _CapturingProviderClient]:
    transport = _CapturingProviderClient(responses)
    provider = ExternalProvider(transport)
    credentials = KisTokenCredentials("test-app-key", "test-app-secret")
    cache = KeyValueStore(FakeKeyValueStoreClient(3600), 3600)
    coordinator = KisTokenCoordinator(
        provider,
        DistributedLock(FakeDistributedLockClient(30), 30),
        cache,
        credentials,
    )
    return (
        KisMarketDataClient(provider, coordinator, credentials, price_cache=cache),
        transport,
    )


@pytest.mark.anyio
async def test_domestic_stock_price_uses_the_official_read_only_request_shape() -> None:
    client, transport = _client(
        [
            ExternalResponse(
                status_code=200,
                headers={},
                content=(
                    b'{"access_token":"token-value","token_type":"Bearer",'
                    b'"expires_in":3600}'
                ),
            ),
            ExternalResponse(
                status_code=200,
                headers={},
                content=b'{"rt_cd":"0","output":{"stck_prpr":"70000"}}',
            ),
        ]
    )

    price = await client.get_domestic_stock_price("005930")

    assert price.stock_code == "005930"
    assert price.current_price == "70000"
    assert price.output == {"stck_prpr": "70000"}
    assert [(request.method, request.path) for request in transport.requests] == [
        ("POST", "/oauth2/tokenP"),
        ("GET", "/uapi/domestic-stock/v1/quotations/inquire-price"),
    ]
    price_request = transport.requests[1]
    assert price_request.headers == {
        "content-type": "application/json",
        "accept": "text/plain",
        "charset": "UTF-8",
        "authorization": "Bearer token-value",
        "appkey": "test-app-key",
        "appsecret": "test-app-secret",
        "tr_id": "FHKST01010100",
        "custtype": "P",
        "tr_cont": "",
    }
    assert price_request.params == {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": "005930",
    }
    assert price_request.retry_safe is True


@pytest.mark.anyio
async def test_domestic_stock_price_reuses_a_short_shared_cache() -> None:
    client, transport = _client(
        [
            ExternalResponse(
                status_code=200,
                headers={},
                content=(
                    b'{"access_token":"token-value","token_type":"Bearer",'
                    b'"expires_in":3600}'
                ),
            ),
            ExternalResponse(
                status_code=200,
                headers={},
                content=b'{"rt_cd":"0","output":{"stck_prpr":"70000"}}',
            ),
        ]
    )

    first = await client.get_domestic_stock_price("005930")
    second = await client.get_domestic_stock_price("005930")

    assert second == first
    assert [(request.method, request.path) for request in transport.requests] == [
        ("POST", "/oauth2/tokenP"),
        ("GET", "/uapi/domestic-stock/v1/quotations/inquire-price"),
    ]


@pytest.mark.anyio
async def test_domestic_stock_price_rejects_a_kis_error_envelope() -> None:
    client, _ = _client(
        [
            ExternalResponse(
                status_code=200,
                headers={},
                content=(
                    b'{"access_token":"token-value","token_type":"Bearer",'
                    b'"expires_in":3600}'
                ),
            ),
            ExternalResponse(
                status_code=200,
                headers={},
                content=b'{"rt_cd":"1","msg1":"market closed"}',
            ),
        ]
    )

    with pytest.raises(KisMarketDataError, match="market closed"):
        await client.get_domestic_stock_price("005930")


@pytest.mark.anyio
async def test_domestic_stock_price_rejects_an_invalid_stock_code_before_io() -> None:
    client, transport = _client([])

    with pytest.raises(ValueError, match="six-digit"):
        await client.get_domestic_stock_price("not-a-stock")

    assert transport.requests == []
