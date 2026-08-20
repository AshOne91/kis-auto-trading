from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

DEFAULT_BACKEND: Final = "redis"
REDIS_URL_ENV: Final = "REDIS_URL"
REDIS_CLUSTER_URL_ENV: Final = "REDIS_CLUSTER_URL"
REDIS_CLUSTER_STARTUP_NODES_ENV: Final = "REDIS_CLUSTER_STARTUP_NODES"
REDIS_SENTINEL_URLS_ENV: Final = "REDIS_SENTINEL_URLS"
MEMCACHED_HOST_ENV: Final = "MEMCACHED_HOST"
MEMCACHED_PORT_ENV: Final = "MEMCACHED_PORT"
DEFAULT_MODE: Final = "standalone"
DEFAULT_SENTINEL_MASTER: Final = "cache-primary"
DEFAULT_KEY_PREFIX: Final = "kis-cache"
DEFAULT_TTL_SECONDS: Final = 86400


class KeyValueStoreBackend(StrEnum):
    REDIS = 'redis'
    MEMCACHED = 'memcached'


class RedisMode(StrEnum):
    STANDALONE = 'standalone'
    SENTINEL = 'sentinel'
    CLUSTER = 'cluster'


@dataclass(frozen=True, slots=True)
class KeyValueStoreConfig:
    backend: KeyValueStoreBackend = KeyValueStoreBackend.REDIS
    mode: RedisMode = RedisMode.STANDALONE
    redis_url: str = ''
    cluster_startup_nodes: tuple[str, ...] = ()
    sentinel_urls: str = ''
    sentinel_master: str = DEFAULT_SENTINEL_MASTER
    memcached_host: str = ''
    memcached_port: int = 11211
    key_prefix: str = DEFAULT_KEY_PREFIX
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    @classmethod
    def from_environment(cls) -> KeyValueStoreConfig:
        backend = KeyValueStoreBackend(DEFAULT_BACKEND)
        if backend is KeyValueStoreBackend.MEMCACHED:
            return cls(
                backend=backend,
                memcached_host=_required_environment(MEMCACHED_HOST_ENV),
                memcached_port=_port_from_environment(MEMCACHED_PORT_ENV),
            )
        mode = RedisMode(DEFAULT_MODE)
        if mode is RedisMode.CLUSTER:
            redis_url = _required_environment(REDIS_CLUSTER_URL_ENV)
            startup_nodes = tuple(
                value.strip()
                for value in os.environ.get(REDIS_CLUSTER_STARTUP_NODES_ENV, '').split(',')
                if value.strip()
            )
            return cls(
                backend=backend, mode=mode, redis_url=redis_url, cluster_startup_nodes=startup_nodes
            )
        if mode is RedisMode.SENTINEL:
            return cls(
                backend=backend, mode=mode,
                sentinel_urls=_required_environment(REDIS_SENTINEL_URLS_ENV),
            )
        return cls(backend=backend, mode=mode, redis_url=_required_environment(REDIS_URL_ENV))


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f'{name} must be set')
    return value


def _port_from_environment(name: str) -> int:
    value = _required_environment(name)
    try:
        port = int(value)
    except ValueError as error:
        raise RuntimeError(f'{name} must be an integer') from error
    if not 1 <= port <= 65535:
        raise RuntimeError(f'{name} must be between 1 and 65535')
    return port
