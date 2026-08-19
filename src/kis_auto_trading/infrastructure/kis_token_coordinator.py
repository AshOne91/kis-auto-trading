from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from kis_auto_trading.infrastructure.distributed_lock import DistributedLock
from kis_auto_trading.infrastructure.external_provider import ExternalProvider
from kis_auto_trading.infrastructure.key_value_store import KeyValueStore

LOGGER = logging.getLogger(__name__)

_TOKEN_PATH = "/oauth2/tokenP"
_TOKEN_GRANT_TYPE = "client_credentials"
_TOKEN_EXPIRY_SAFETY_SECONDS = 60
_REFRESH_LOCK_TTL_SECONDS = 30
_REFRESH_WAIT_TIMEOUT_SECONDS = 10.0
_REFRESH_WAIT_INTERVAL_SECONDS = 0.1


def _utc_now() -> datetime:
    return datetime.now(UTC)


class KisTokenCoordinatorError(RuntimeError):
    """Raised when KIS OAuth token coordination cannot complete safely."""


class KisTokenConfigurationError(KisTokenCoordinatorError):
    """Raised when required KIS credentials are not configured."""


class KisTokenRefreshInProgress(KisTokenCoordinatorError):
    """Raised when another replica did not publish a refreshed token in time."""


@dataclass(frozen=True, slots=True)
class KisTokenCredentials:
    app_key: str
    app_secret: str
    scope: str = "default"

    @classmethod
    def from_environment(cls) -> KisTokenCredentials:
        app_key = os.environ.get("KIS_APP_KEY")
        app_secret = os.environ.get("KIS_APP_SECRET")
        missing = [
            name
            for name, value in (("KIS_APP_KEY", app_key), ("KIS_APP_SECRET", app_secret))
            if not value
        ]
        if missing:
            raise KisTokenConfigurationError(
                "Missing required KIS environment variables: " + ", ".join(missing)
            )
        return cls(
            app_key=app_key,
            app_secret=app_secret,
            scope=os.environ.get("KIS_TOKEN_SCOPE", "default"),
        )


@dataclass(frozen=True, slots=True)
class KisAccessToken:
    value: str
    token_type: str
    expires_at: datetime


class KisTokenCoordinator:
    """Coordinates one KIS OAuth token refresh across application replicas."""

    def __init__(
        self,
        provider: ExternalProvider,
        lock: DistributedLock,
        cache: KeyValueStore,
        credentials: KisTokenCredentials,
        *,
        now: Callable[[], datetime] = _utc_now,
        refresh_wait_timeout_seconds: float = _REFRESH_WAIT_TIMEOUT_SECONDS,
    ) -> None:
        if refresh_wait_timeout_seconds < 0:
            raise ValueError("refresh_wait_timeout_seconds must not be negative")
        self._provider = provider
        self._lock = lock
        self._cache = cache
        self._credentials = credentials
        self._now = now
        self._refresh_wait_timeout_seconds = refresh_wait_timeout_seconds
        identity = f"{credentials.scope}:{credentials.app_key}".encode()
        suffix = hashlib.sha256(identity).hexdigest()[:16]
        self._cache_key = f"oauth:token:{suffix}"
        self._lock_key = f"oauth:refresh:{suffix}"

    @classmethod
    def from_environment(cls) -> KisTokenCoordinator:
        return cls(
            ExternalProvider.from_environment(),
            DistributedLock.from_environment(),
            KeyValueStore.from_environment(),
            KisTokenCredentials.from_environment(),
        )

    async def get_access_token(self) -> KisAccessToken:
        cached = await self._read_cached_token()
        if cached is not None:
            return cached

        lock_token = await self._lock.acquire(
            self._lock_key,
            ttl_seconds=_REFRESH_LOCK_TTL_SECONDS,
        )
        if lock_token is None:
            return await self._wait_for_refresh()
        try:
            cached = await self._read_cached_token()
            if cached is not None:
                return cached
            return await self._request_and_cache_token()
        finally:
            await self._lock.release(self._lock_key, lock_token)

    async def aclose(self) -> None:
        await self._provider.aclose()
        await self._lock.aclose()
        await self._cache.aclose()

    async def _wait_for_refresh(self) -> KisAccessToken:
        deadline = asyncio.get_running_loop().time() + self._refresh_wait_timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(_REFRESH_WAIT_INTERVAL_SECONDS)
            cached = await self._read_cached_token()
            if cached is not None:
                return cached
        raise KisTokenRefreshInProgress("KIS token refresh is already in progress")

    async def _request_and_cache_token(self) -> KisAccessToken:
        response = await self._provider.request(
            "POST",
            _TOKEN_PATH,
            json={
                "grant_type": _TOKEN_GRANT_TYPE,
                "appkey": self._credentials.app_key,
                "appsecret": self._credentials.app_secret,
            },
            retry_safe=False,
        )
        if not 200 <= response.status_code < 300:
            raise KisTokenCoordinatorError(
                f"KIS token request returned HTTP {response.status_code}"
            )
        token = self._parse_token_response(response.content)
        ttl_seconds = max(
            1,
            math.floor((token.expires_at - self._now()).total_seconds())
            - _TOKEN_EXPIRY_SAFETY_SECONDS,
        )
        await self._cache.set(
            self._cache_key,
            json.dumps(
                {
                    "access_token": token.value,
                    "token_type": token.token_type,
                    "expires_at": token.expires_at.isoformat(),
                },
                separators=(",", ":"),
            ),
            ttl_seconds=ttl_seconds,
        )
        LOGGER.info("KIS OAuth access token refreshed")
        return token

    async def _read_cached_token(self) -> KisAccessToken | None:
        value = await self._cache.get(self._cache_key)
        if value is None:
            return None
        try:
            payload = json.loads(value)
            access_token = payload["access_token"]
            token_type = payload["token_type"]
            expires_at = datetime.fromisoformat(payload["expires_at"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            await self._cache.delete(self._cache_key)
            return None
        if (
            not isinstance(access_token, str)
            or not access_token
            or not isinstance(token_type, str)
            or not token_type
            or expires_at.tzinfo is None
            or expires_at <= self._now()
        ):
            await self._cache.delete(self._cache_key)
            return None
        return KisAccessToken(
            value=access_token,
            token_type=token_type,
            expires_at=expires_at.astimezone(UTC),
        )

    def _parse_token_response(self, content: bytes) -> KisAccessToken:
        try:
            payload = json.loads(content)
            access_token = payload["access_token"]
            token_type = payload["token_type"]
            expires_in = payload["expires_in"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise KisTokenCoordinatorError("KIS token response is invalid") from error
        if (
            not isinstance(access_token, str)
            or not access_token
            or not isinstance(token_type, str)
            or not token_type
            or isinstance(expires_in, bool)
            or not isinstance(expires_in, int | float)
            or not math.isfinite(expires_in)
            or expires_in <= 0
        ):
            raise KisTokenCoordinatorError("KIS token response is invalid")
        return KisAccessToken(
            value=access_token,
            token_type=token_type,
            expires_at=self._now() + timedelta(seconds=expires_in),
        )