import base64
import secrets
from dataclasses import dataclass
from typing import Protocol


class SessionStoreError(RuntimeError):
    pass


def _user_routing_tag(user_id: str) -> str:
    if not user_id:
        raise ValueError("user_id must not be empty")
    return base64.urlsafe_b64encode(user_id.encode("utf-8")).decode(
        "ascii"
    ).rstrip("=")


def _session_routing_tag(session_id: str) -> str:
    tag, separator, secret = session_id.partition(".")
    if not separator or not tag or not secret:
        raise ValueError(
            "session_id must be created by create_session_id"
        )
    return tag


def create_session_id(user_id: str) -> str:
    return (
        f"{_user_routing_tag(user_id)}."
        f"{secrets.token_urlsafe(32)}"
    )


@dataclass(frozen=True, slots=True)
class SessionData:
    session_id: str
    user_id: str
    data: dict[str, object]


class SessionStore(Protocol):
    async def health_check(self) -> None: ...

    async def create(self, session: SessionData) -> None: ...

    async def get(self, session_id: str) -> SessionData | None: ...

    async def refresh(self, session_id: str) -> bool: ...

    async def revoke(self, session_id: str) -> bool: ...

    async def revoke_user_sessions(self, user_id: str) -> int: ...
