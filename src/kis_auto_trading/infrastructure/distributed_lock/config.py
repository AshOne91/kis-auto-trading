from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

REDIS_URL_ENV: Final = "REDIS_URL"
REDIS_CLUSTER_URL_ENV: Final = "REDIS_CLUSTER_URL"
REDIS_CLUSTER_STARTUP_NODES_ENV: Final = "REDIS_CLUSTER_STARTUP_NODES"
REDIS_SENTINEL_URLS_ENV: Final = "REDIS_SENTINEL_URLS"
DEFAULT_MODE: Final = "standalone"
DEFAULT_SENTINEL_MASTER: Final = "lock-primary"
DEFAULT_KEY_PREFIX: Final = "kis-lock"
DEFAULT_TTL_SECONDS: Final = 30


class RedisMode(StrEnum):
    STANDALONE = 'standalone'
    SENTINEL = 'sentinel'
    CLUSTER = 'cluster'


@dataclass(frozen=True, slots=True)
class DistributedLockConfig:
    mode: RedisMode = RedisMode.STANDALONE
    redis_url: str = ''
    cluster_startup_nodes: tuple[str, ...] = ()
    sentinel_urls: str = ''
    sentinel_master: str = DEFAULT_SENTINEL_MASTER
    key_prefix: str = DEFAULT_KEY_PREFIX
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    @classmethod
    def from_environment(cls) -> DistributedLockConfig:
        mode = RedisMode(DEFAULT_MODE)
        if mode is RedisMode.CLUSTER:
            redis_url = _required_environment(REDIS_CLUSTER_URL_ENV)
            startup_nodes = tuple(
                value.strip()
                for value in os.environ.get(REDIS_CLUSTER_STARTUP_NODES_ENV, '').split(',')
                if value.strip()
            )
            return cls(
                mode=mode,
                redis_url=redis_url,
                cluster_startup_nodes=startup_nodes,
            )
        if mode is RedisMode.SENTINEL:
            return cls(
                mode=mode,
                sentinel_urls=_required_environment(REDIS_SENTINEL_URLS_ENV),
            )
        return cls(mode=mode, redis_url=_required_environment(REDIS_URL_ENV))


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f'{name} must be set')
    return value
