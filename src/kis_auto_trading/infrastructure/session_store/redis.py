import json

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster
from redis.exceptions import RedisError

from .protocol import (
    SessionData,
    SessionStoreError,
    _session_routing_tag,
    _user_routing_tag,
)


class RedisSessionStore:
    _namespace = "kis_session"
    _ttl_seconds = 3600

    def __init__(self, client: Redis | RedisCluster) -> None:
        self._client = client

    async def health_check(self) -> None:
        try:
            if not await self._client.ping():
                raise SessionStoreError('Redis session health check failed')
        except RedisError as error:
            raise SessionStoreError('Redis session health check failed') from error

    async def create(self, session: SessionData) -> None:
        if _session_routing_tag(session.session_id) != _user_routing_tag(
            session.user_id
        ):
            raise SessionStoreError(
                "Session ID does not belong to the session user"
            )
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
        routing_tag = _session_routing_tag(session_id)
        return f"{self._namespace}:{{{routing_tag}}}:session:{session_id}"

    def _user_key(self, user_id: str) -> str:
        routing_tag = _user_routing_tag(user_id)
        return f"{self._namespace}:{{{routing_tag}}}:user-sessions"
