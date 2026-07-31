from dataclasses import dataclass
from typing import Protocol


class SessionStoreError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SessionData:
    session_id: str
    user_id: str
    data: dict[str, object]


class SessionStore(Protocol):
    async def create(self, session: SessionData) -> None: ...

    async def get(self, session_id: str) -> SessionData | None: ...

    async def refresh(self, session_id: str) -> bool: ...

    async def revoke(self, session_id: str) -> bool: ...

    async def revoke_user_sessions(self, user_id: str) -> int: ...
