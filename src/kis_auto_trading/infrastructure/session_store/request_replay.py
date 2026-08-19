import hashlib
import json
import secrets
from typing import Final

from redis.exceptions import RedisError

from .protocol import (
    ReplayClaim,
    ReplayRecord,
    RequestReplayConflict,
    RequestReplayInProgress,
    SessionStoreError,
)

_COMPLETE_SCRIPT: Final = """
local value = redis.call('get', KEYS[1])
if not value then return 0 end
local payload = cjson.decode(value)
if payload['token'] ~= ARGV[1] then return 0 end
payload['status'] = 'completed'
payload['status_code'] = tonumber(ARGV[2])
payload['body'] = ARGV[3]
redis.call('set', KEYS[1], cjson.encode(payload), 'EX', ARGV[4])
return 1
"""
_ABORT_SCRIPT: Final = """
local value = redis.call('get', KEYS[1])
if not value then return 0 end
local payload = cjson.decode(value)
if payload['token'] ~= ARGV[1] then return 0 end
return redis.call('del', KEYS[1])
"""


class RedisRequestReplayStore:
    def __init__(self, client: object, namespace: str) -> None:
        self._client = client
        self._namespace = namespace

    async def claim(
        self, key: str, fingerprint: str, ttl_seconds: int
    ) -> ReplayClaim | ReplayRecord:
        if not key.strip():
            raise ValueError("idempotency key must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("idempotency ttl must be positive")
        token = secrets.token_urlsafe(24)
        redis_key = self._key(key)
        payload = json.dumps(
            {'fingerprint': fingerprint, 'status': 'pending', 'token': token},
            separators=(',', ':'),
        )
        try:
            created = await self._client.set(
                redis_key, payload, ex=ttl_seconds, nx=True
            )
            if created:
                return ReplayClaim(key, fingerprint, token, ttl_seconds)
            raw = await self._client.get(redis_key)
        except RedisError as error:
            raise SessionStoreError("request replay claim failed") from error
        if raw is None:
            raise RequestReplayInProgress("request replay claim is changing")
        try:
            existing = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise SessionStoreError("request replay record is invalid") from error
        if existing.get('fingerprint') != fingerprint:
            raise RequestReplayConflict("idempotency key was reused with a different request")
        if existing.get('status') == 'completed':
            return ReplayRecord(
                status_code=int(existing['status_code']),
                body=str(existing['body']),
            )
        raise RequestReplayInProgress("request with this idempotency key is in progress")

    async def complete(
        self, claim: ReplayClaim, status_code: int, body: str
    ) -> None:
        try:
            updated = await self._client.eval(
                _COMPLETE_SCRIPT, 1, self._key(claim.key), claim.token,
                str(status_code), body, str(claim.ttl_seconds),
            )
        except RedisError as error:
            raise SessionStoreError("request replay completion failed") from error
        if not updated:
            raise SessionStoreError("request replay claim was lost")

    async def abort(self, claim: ReplayClaim) -> None:
        try:
            await self._client.eval(
                _ABORT_SCRIPT, 1, self._key(claim.key), claim.token
            )
        except RedisError as error:
            raise SessionStoreError("request replay abort failed") from error

    def _key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return f"{self._namespace}:{{replay}}:request:{digest}"
