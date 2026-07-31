from collections.abc import Callable
from time import monotonic

from .protocol import SessionData


class FakeSessionStore:
    def __init__(
        self, ttl_seconds: int, clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._sessions: dict[str, tuple[SessionData, float]] = {}
        self._user_sessions: dict[str, set[str]] = {}

    async def create(self, session: SessionData) -> None:
        await self.revoke(session.session_id)
        expires_at = self._clock() + self._ttl_seconds
        self._sessions[session.session_id] = (session, expires_at)
        self._user_sessions.setdefault(session.user_id, set()).add(
            session.session_id
        )

    async def get(self, session_id: str) -> SessionData | None:
        stored = self._sessions.get(session_id)
        if stored is None:
            return None
        session, expires_at = stored
        if expires_at <= self._clock():
            await self.revoke(session_id)
            return None
        return session

    async def refresh(self, session_id: str) -> bool:
        session = await self.get(session_id)
        if session is None:
            return False
        self._sessions[session_id] = (
            session, self._clock() + self._ttl_seconds
        )
        return True

    async def revoke(self, session_id: str) -> bool:
        stored = self._sessions.pop(session_id, None)
        if stored is None:
            return False
        session, _ = stored
        user_sessions = self._user_sessions.get(session.user_id)
        if user_sessions is not None:
            user_sessions.discard(session_id)
            if not user_sessions:
                self._user_sessions.pop(session.user_id, None)
        return True

    async def revoke_user_sessions(self, user_id: str) -> int:
        session_ids = tuple(self._user_sessions.get(user_id, set()))
        for session_id in session_ids:
            await self.revoke(session_id)
        return len(session_ids)
