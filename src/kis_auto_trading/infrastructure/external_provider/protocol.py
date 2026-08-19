from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExternalResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes


class ExternalProviderClient(Protocol):
    async def health_check(self) -> None: ...

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
    ) -> ExternalResponse: ...

    async def aclose(self) -> None: ...
