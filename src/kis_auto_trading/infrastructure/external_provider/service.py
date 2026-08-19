from __future__ import annotations

from collections.abc import Mapping

from .config import ExternalProviderConfig
from .protocol import ExternalProviderClient, ExternalResponse


class ExternalProvider:
    def __init__(self, client: ExternalProviderClient) -> None:
        self._client = client

    @classmethod
    def from_environment(cls) -> ExternalProvider:
        from .http_client import HttpExternalProviderClient

        return cls(HttpExternalProviderClient(ExternalProviderConfig.from_environment()))

    async def health_check(self) -> None:
        await self._client.health_check()

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
        return await self._client.request(
            method,
            path,
            headers=headers,
            params=params,
            json=json,
            content=content,
            retry_safe=retry_safe,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
