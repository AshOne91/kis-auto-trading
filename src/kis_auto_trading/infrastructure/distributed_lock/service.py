from __future__ import annotations

from .config import DistributedLockConfig
from .protocol import DistributedLockClient


class DistributedLock:
    def __init__(
        self, client: DistributedLockClient, default_ttl_seconds: int
    ) -> None:
        self._client = client
        self._default_ttl_seconds = default_ttl_seconds

    @classmethod
    def from_environment(cls) -> DistributedLock:
        from .redis import RedisDistributedLockClient

        config = DistributedLockConfig.from_environment()
        return cls(RedisDistributedLockClient(config), config.ttl_seconds)

    async def health_check(self) -> None:
        await self._client.health_check()

    async def acquire(
        self, key: str, *, ttl_seconds: int | None = None
    ) -> str | None:
        return await self._client.acquire(
            key,
            ttl_seconds=(
                self._default_ttl_seconds
                if ttl_seconds is None
                else ttl_seconds
            ),
        )

    async def release(self, key: str, token: str) -> bool:
        return await self._client.release(key, token)

    async def aclose(self) -> None:
        await self._client.aclose()
