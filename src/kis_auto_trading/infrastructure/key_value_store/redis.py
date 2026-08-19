from __future__ import annotations

from urllib.parse import urlparse

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster
from redis.asyncio.sentinel import Sentinel
from redis.cluster import ClusterNode

from .config import KeyValueStoreConfig, RedisMode


class RedisKeyValueStoreClient:
    def __init__(
        self, config: KeyValueStoreConfig, *, client: Redis | RedisCluster | None = None
    ) -> None:
        self._config = config
        self._sentinel: Sentinel | None = None
        if client is not None:
            self._client = client
            self._owns_client = False
        elif config.mode is RedisMode.CLUSTER:
            self._client = RedisCluster.from_url(
                config.redis_url,
                startup_nodes=self._cluster_startup_nodes() or None,
                decode_responses=True,
                require_full_coverage=True,
                reinitialize_steps=1,
            )
            self._owns_client = True
        elif config.mode is RedisMode.SENTINEL:
            self._sentinel = Sentinel(
                self._sentinel_endpoints(config.sentinel_urls),
                socket_timeout=2, decode_responses=True
            )
            self._client = self._sentinel.master_for(
                config.sentinel_master, socket_timeout=2, decode_responses=True
            )
            self._owns_client = True
        else:
            self._client = Redis.from_url(config.redis_url, decode_responses=True)
            self._owns_client = True

    async def health_check(self) -> None:
        if not await self._client.ping():
            raise RuntimeError('Redis key-value store health check failed')

    async def get(self, key: str) -> str | None:
        return await self._client.get(self._key(key))

    async def set(
        self, key: str, value: str, *, ttl_seconds: int | None = None
    ) -> None:
        await self._client.set(
            self._key(key), value, ex=self._ttl(ttl_seconds)
        )

    async def delete(self, key: str) -> bool:
        return bool(await self._client.delete(self._key(key)))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
            if self._sentinel is not None:
                for sentinel_client in self._sentinel.sentinels:
                    await sentinel_client.aclose()

    def _key(self, key: str) -> str:
        if not key:
            raise ValueError('cache key must not be empty')
        return f'{self._config.key_prefix}:{key}'

    def _ttl(self, ttl_seconds: int | None) -> int:
        ttl = ttl_seconds if ttl_seconds is not None else self._config.ttl_seconds
        if ttl <= 0:
            raise ValueError('ttl_seconds must be positive')
        return ttl

    def _cluster_startup_nodes(self) -> list[ClusterNode]:
        nodes: list[ClusterNode] = []
        for value in self._config.cluster_startup_nodes:
            parsed = urlparse(value)
            if parsed.hostname:
                nodes.append(ClusterNode(parsed.hostname, parsed.port or 6379))
        return nodes

    @staticmethod
    def _sentinel_endpoints(value: str) -> list[tuple[str, int]]:
        endpoints: list[tuple[str, int]] = []
        for item in value.split(','):
            host, separator, port_text = item.strip().rpartition(':')
            if not separator or not host:
                raise ValueError(f'Invalid Redis Sentinel endpoint: {item!r}')
            try:
                endpoints.append((host, int(port_text)))
            except ValueError as error:
                raise ValueError(
                    f'Invalid Redis Sentinel port: {item!r}'
                ) from error
        if not endpoints:
            raise ValueError('Redis Sentinel endpoints are empty')
        return endpoints
