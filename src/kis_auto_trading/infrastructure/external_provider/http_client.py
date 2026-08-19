from __future__ import annotations

import asyncio
from collections.abc import Mapping

import httpx

from .config import ExternalProviderConfig
from .protocol import ExternalResponse

_DEFAULT_RETRY_SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


class HttpExternalProviderClient:
    def __init__(
        self,
        config: ExternalProviderConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds
        )
        self._owns_client = client is None

    async def health_check(self) -> None:
        response = await self.request('GET', self._config.health_path)
        if not 200 <= response.status_code < 400:
            raise RuntimeError(
                f'external provider health check returned {response.status_code}'
            )

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
        if not path.startswith('/'):
            raise ValueError('external provider path must start with /')
        normalized_method = method.upper()
        retries_allowed = (
            retry_safe
            if retry_safe is not None
            else normalized_method in _DEFAULT_RETRY_SAFE_METHODS
        )

        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._client.request(
                    normalized_method,
                    path,
                    headers=dict(headers) if headers else None,
                    params=dict(params) if params else None,
                    json=json,
                    content=content,
                )
            except httpx.RequestError:
                if not retries_allowed or attempt == self._config.max_retries:
                    raise
            else:
                result = ExternalResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content=response.content,
                )
                if (
                    not retries_allowed
                    or not self._is_retryable_status(result.status_code)
                    or attempt == self._config.max_retries
                ):
                    return result

            await asyncio.sleep(
                self._config.retry_delay_seconds * (2**attempt)
            )

        raise AssertionError('request retry loop must return or raise')

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in {408, 425, 429} or status_code >= 500
