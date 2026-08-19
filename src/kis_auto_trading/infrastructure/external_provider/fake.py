from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping

from .protocol import ExternalResponse


class FakeExternalProviderClient:
    """Deterministic transport fake; provider semantics belong to the consumer."""

    def __init__(self, responses: Iterable[ExternalResponse] = ()) -> None:
        self._responses = deque(responses)
        self.requests: list[tuple[str, str]] = []

    async def health_check(self) -> None:
        return None

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
        del headers, params, json, content, retry_safe
        self.requests.append((method.upper(), path))
        if self._responses:
            return self._responses.popleft()
        return ExternalResponse(status_code=200, headers={}, content=b'')

    async def aclose(self) -> None:
        return None
