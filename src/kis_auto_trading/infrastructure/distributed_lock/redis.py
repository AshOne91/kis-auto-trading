from __future__ import annotations

import secrets
from urllib.parse import urlparse

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster
from redis.asyncio.sentinel import Sentinel
from redis.cluster import ClusterNode

from .config import DistributedLockConfig, RedisMode

_RELEASE_IF_OWNER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class RedisDistributedLockClient:
    def __init__(
        self,
        config: DistributedLockConfig,
        *,
        client: Redis | RedisCluster | None = None,
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
                socket_timeout=2,
                decode_responses=True,
            )
            self._client = self._sentinel.master_for(
                config.sentinel_master,
                socket_timeout=2,
                decode_responses=True,
            )
            self._owns_client = True
        else:
            self._client = Redis.from_url(config.redis_url, decode_responses=True)
            self._owns_client = True

    async def health_check(self) -> None:
        if not await self._client.ping():
            raise RuntimeError('Redis lock health check failed')

    async def acquire(
        self, key: str, *, ttl_seconds: int | None = None
    ) -> str | None:
        ttl = self._ttl(ttl_seconds)
        token = secrets.token_urlsafe(32)
        acquired = await self._client.set(
            self._key(key), token, nx=True, ex=ttl
        )
        return token if acquired else None

    async def release(self, key: str, token: str) -> bool:
        released = await self._client.eval(
            _RELEASE_IF_OWNER, 1, self._key(key), token
        )
        return bool(released)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
            if self._sentinel is not None:
                for sentinel_client in self._sentinel.sentinels:
                    await sentinel_client.aclose()

    def _key(self, key: str) -> str:
        if not key:
            raise ValueError('lock key must not be empty')
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
