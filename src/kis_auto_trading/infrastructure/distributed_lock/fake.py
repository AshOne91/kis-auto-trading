from __future__ import annotations

from collections.abc import Callable
from time import monotonic


class FakeDistributedLockClient:
    """Deterministic lease fake with owner-only release semantics."""

    def __init__(
        self,
        default_ttl_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if default_ttl_seconds <= 0:
            raise ValueError('default_ttl_seconds must be positive')
        self._default_ttl_seconds = default_ttl_seconds
        self._clock = clock
        self._leases: dict[str, tuple[str, float]] = {}
        self._next_token = 0

    async def health_check(self) -> None:
        return None

    async def acquire(
        self, key: str, *, ttl_seconds: int | None = None
    ) -> str | None:
        self._require_key(key)
        self._expire(key)
        if key in self._leases:
            return None
        ttl = self._ttl(ttl_seconds)
        self._next_token += 1
        token = f'lock-token-{self._next_token}'
        self._leases[key] = (token, self._clock() + ttl)
        return token

    async def release(self, key: str, token: str) -> bool:
        self._require_key(key)
        self._expire(key)
        lease = self._leases.get(key)
        if lease is None or lease[0] != token:
            return False
        del self._leases[key]
        return True

    async def aclose(self) -> None:
        return None

    def _expire(self, key: str) -> None:
        lease = self._leases.get(key)
        if lease is not None and lease[1] <= self._clock():
            del self._leases[key]

    def _ttl(self, ttl_seconds: int | None) -> int:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        if ttl <= 0:
            raise ValueError('ttl_seconds must be positive')
        return ttl

    @staticmethod
    def _require_key(key: str) -> None:
        if not key:
            raise ValueError('lock key must not be empty')
