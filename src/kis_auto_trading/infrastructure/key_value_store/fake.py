from __future__ import annotations

from collections.abc import Callable
from time import monotonic


class FakeKeyValueStoreClient:
    """Deterministic TTL key-value fake."""

    def __init__(
        self,
        default_ttl_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if default_ttl_seconds <= 0:
            raise ValueError('default_ttl_seconds must be positive')
        self._default_ttl_seconds = default_ttl_seconds
        self._clock = clock
        self._values: dict[str, tuple[str, float]] = {}

    async def health_check(self) -> None:
        return None

    async def get(self, key: str) -> str | None:
        self._require_key(key)
        stored = self._values.get(key)
        if stored is None:
            return None
        value, expires_at = stored
        if expires_at <= self._clock():
            del self._values[key]
            return None
        return value

    async def set(
        self, key: str, value: str, *, ttl_seconds: int | None = None
    ) -> None:
        self._require_key(key)
        self._values[key] = (value, self._clock() + self._ttl(ttl_seconds))

    async def delete(self, key: str) -> bool:
        self._require_key(key)
        return self._values.pop(key, None) is not None

    async def aclose(self) -> None:
        return None

    def _ttl(self, ttl_seconds: int | None) -> int:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        if ttl <= 0:
            raise ValueError('ttl_seconds must be positive')
        return ttl

    @staticmethod
    def _require_key(key: str) -> None:
        if not key:
            raise ValueError('cache key must not be empty')
