from __future__ import annotations

from .config import KeyValueStoreBackend, KeyValueStoreConfig
from .protocol import KeyValueStoreClient


class KeyValueStore:
    def __init__(
        self, client: KeyValueStoreClient, default_ttl_seconds: int
    ) -> None:
        self._client = client
        self._default_ttl_seconds = default_ttl_seconds

    @classmethod
    def from_environment(cls) -> KeyValueStore:
        config = KeyValueStoreConfig.from_environment()
        if config.backend is KeyValueStoreBackend.MEMCACHED:
            from .memcached import MemcachedKeyValueStoreClient

            return cls(MemcachedKeyValueStoreClient(config), config.ttl_seconds)
        from .redis import RedisKeyValueStoreClient

        return cls(RedisKeyValueStoreClient(config), config.ttl_seconds)

    async def health_check(self) -> None:
        await self._client.health_check()

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(
        self, key: str, value: str, *, ttl_seconds: int | None = None
    ) -> None:
        await self._client.set(
            key,
            value,
            ttl_seconds=(
                self._default_ttl_seconds
                if ttl_seconds is None
                else ttl_seconds
            ),
        )

    async def delete(self, key: str) -> bool:
        return await self._client.delete(key)

    async def aclose(self) -> None:
        await self._client.aclose()
