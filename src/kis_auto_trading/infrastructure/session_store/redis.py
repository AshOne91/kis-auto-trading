import json

from redis.asyncio import Redis
from redis.exceptions import RedisError

from .protocol import SessionData, SessionStoreError


class RedisSessionStore:
    _namespace = "kis_session"
    _ttl_seconds = 3600

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def create(self, session: SessionData) -> None:
        payload = json.dumps(
            {"user_id": session.user_id, "data": session.data},
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            async with self._client.pipeline(transaction=True) as pipe:
                pipe.set(
                    self._session_key(session.session_id),
                    payload,
                    ex=self._ttl_seconds,
                )
                pipe.sadd(self._user_key(session.user_id), session.session_id)
                pipe.expire(self._user_key(session.user_id), self._ttl_seconds)
                await pipe.execute()
        except RedisError as error:
            raise SessionStoreError("Redis session create failed") from error

    async def get(self, session_id: str) -> SessionData | None:
        try:
            payload = await self._client.get(self._session_key(session_id))
        except RedisError as error:
            raise SessionStoreError("Redis session get failed") from error
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        decoded = json.loads(payload)
        return SessionData(
            session_id=session_id,
            user_id=decoded["user_id"],
            data=decoded["data"],
        )

    async def refresh(self, session_id: str) -> bool:
        session = await self.get(session_id)
        if session is None:
            return False
        try:
            async with self._client.pipeline(transaction=True) as pipe:
                pipe.expire(self._session_key(session_id), self._ttl_seconds)
                pipe.expire(self._user_key(session.user_id), self._ttl_seconds)
                results = await pipe.execute()
            return bool(results[0])
        except RedisError as error:
            raise SessionStoreError("Redis session refresh failed") from error

    async def revoke(self, session_id: str) -> bool:
        session = await self.get(session_id)
        if session is None:
            return False
        try:
            async with self._client.pipeline(transaction=True) as pipe:
                pipe.delete(self._session_key(session_id))
                pipe.srem(self._user_key(session.user_id), session_id)
                results = await pipe.execute()
            return bool(results[0])
        except RedisError as error:
            raise SessionStoreError("Redis session revoke failed") from error

    async def revoke_user_sessions(self, user_id: str) -> int:
        user_key = self._user_key(user_id)
        try:
            session_ids = await self._client.smembers(user_key)
            normalized = [
                value.decode("utf-8") if isinstance(value, bytes) else value
                for value in session_ids
            ]
            if not normalized:
                return 0
            keys = [self._session_key(value) for value in normalized]
            await self._client.delete(*keys, user_key)
            return len(normalized)
        except RedisError as error:
            raise SessionStoreError("Redis user session revoke failed") from error

    def _session_key(self, session_id: str) -> str:
        return f"{self._namespace}:session:{session_id}"

    def _user_key(self, user_id: str) -> str:
        return f"{self._namespace}:user-sessions:{user_id}"
