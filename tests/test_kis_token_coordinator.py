from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kis_auto_trading.infrastructure.distributed_lock import (
    DistributedLock,
    FakeDistributedLockClient,
)
from kis_auto_trading.infrastructure.external_provider import (
    ExternalProvider,
    ExternalResponse,
    FakeExternalProviderClient,
)
from kis_auto_trading.infrastructure.key_value_store import (
    FakeKeyValueStoreClient,
    KeyValueStore,
)
from kis_auto_trading.infrastructure.kis_token_coordinator import (
    KisTokenCoordinator,
    KisTokenCoordinatorError,
    KisTokenCredentials,
    KisTokenRefreshInProgress,
)


def _coordinator(
    responses: list[ExternalResponse],
    *,
    lock: DistributedLock | _BusyLock | None = None,
    cache: KeyValueStore | None = None,
    refresh_wait_timeout_seconds: float = 10,
) -> tuple[KisTokenCoordinator, FakeExternalProviderClient]:
    provider_client = FakeExternalProviderClient(responses)
    coordinator = KisTokenCoordinator(
        ExternalProvider(provider_client),
        lock or DistributedLock(FakeDistributedLockClient(30), 30),
        cache or KeyValueStore(FakeKeyValueStoreClient(3600), 3600),
        KisTokenCredentials("test-app-key", "test-app-secret", scope="sandbox"),
        now=lambda: datetime(2026, 8, 20, tzinfo=UTC),
        refresh_wait_timeout_seconds=refresh_wait_timeout_seconds,
    )
    return coordinator, provider_client


@pytest.mark.anyio
async def test_token_coordinator_caches_a_valid_kis_token() -> None:
    coordinator, provider_client = _coordinator(
        [
            ExternalResponse(
                status_code=200,
                headers={},
                content=(
                    b'{"access_token":"token-value","token_type":"Bearer",'
                    b'"expires_in":3600}'
                ),
            )
        ]
    )

    first = await coordinator.get_access_token()
    second = await coordinator.get_access_token()

    assert first.value == "token-value"
    assert second == first
    assert provider_client.requests == [("POST", "/oauth2/tokenP")]


@pytest.mark.anyio
async def test_token_coordinator_releases_lock_when_kis_response_is_invalid() -> None:
    lock = DistributedLock(FakeDistributedLockClient(30), 30)
    coordinator, provider_client = _coordinator(
        [
            ExternalResponse(status_code=200, headers={}, content=b"{}"),
            ExternalResponse(
                status_code=200,
                headers={},
                content=(
                    b'{"access_token":"token-value","token_type":"Bearer",'
                    b'"expires_in":3600}'
                ),
            ),
        ],
        lock=lock,
    )

    with pytest.raises(KisTokenCoordinatorError, match="response is invalid"):
        await coordinator.get_access_token()

    assert (await coordinator.get_access_token()).value == "token-value"
    assert provider_client.requests == [
        ("POST", "/oauth2/tokenP"),
        ("POST", "/oauth2/tokenP"),
    ]

class _CapturingProviderClient:
    def __init__(self, response: ExternalResponse) -> None:
        self.response = response
        self.request_body: object | None = None
        self.retry_safe: bool | None = None

    async def health_check(self) -> None:
        pass

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: object | None = None,
        retry_safe: bool | None = None,
        **_: object,
    ) -> ExternalResponse:
        assert (method, path) == ("POST", "/oauth2/tokenP")
        self.request_body = json
        self.retry_safe = retry_safe
        return self.response

    async def aclose(self) -> None:
        pass


@pytest.mark.anyio
async def test_token_coordinator_uses_the_official_kis_request_shape() -> None:
    client = _CapturingProviderClient(
        ExternalResponse(
            status_code=200,
            headers={},
            content=(
                b'{"access_token":"token-value","token_type":"Bearer",'
                b'"expires_in":3600}'
            ),
        )
    )
    coordinator = KisTokenCoordinator(
        ExternalProvider(client),
        DistributedLock(FakeDistributedLockClient(30), 30),
        KeyValueStore(FakeKeyValueStoreClient(3600), 3600),
        KisTokenCredentials("test-app-key", "test-app-secret"),
        now=lambda: datetime(2026, 8, 20, tzinfo=UTC),
    )

    await coordinator.get_access_token()

    assert client.request_body == {
        "grant_type": "client_credentials",
        "appkey": "test-app-key",
        "appsecret": "test-app-secret",
    }
    assert client.retry_safe is False

class _BusyLock:
    async def acquire(self, key: str, *, ttl_seconds: int | None = None) -> None:
        del key, ttl_seconds

    async def release(self, key: str, token: str) -> bool:
        del key, token
        return False
    async def aclose(self) -> None:
        pass


@pytest.mark.anyio
async def test_token_coordinator_reports_an_in_progress_refresh() -> None:
    coordinator, _ = _coordinator(
        [],
        lock=_BusyLock(),
        refresh_wait_timeout_seconds=0,
    )

    with pytest.raises(KisTokenRefreshInProgress):
        await coordinator.get_access_token()