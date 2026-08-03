from typing import cast

from redis.asyncio import Redis
from redis.crc import key_slot

from kis_auto_trading.infrastructure.session_store.protocol import (
    SessionData,
    _session_routing_tag,
    _user_routing_tag,
    create_session_id,
)
from kis_auto_trading.infrastructure.session_store.redis import RedisSessionStore


def test_session_and_user_index_share_cluster_slot() -> None:
    user_id = "1b3300c2-c750-4c2e-9f6e-55927bc32a29"
    session_id = create_session_id(user_id)
    store = RedisSessionStore(cast(Redis, object()))

    session_key = store._session_key(session_id)
    user_key = store._user_key(user_id)

    assert _session_routing_tag(session_id) == _user_routing_tag(user_id)
    assert key_slot(session_key.encode()) == key_slot(user_key.encode())


def test_session_id_keeps_random_secret_and_user_routing_tag() -> None:
    user_id = "user-1"

    first = create_session_id(user_id)
    second = create_session_id(user_id)

    assert first != second
    assert _session_routing_tag(first) == _session_routing_tag(second)


def test_session_data_accepts_generated_session_id() -> None:
    user_id = "user-1"
    session_id = create_session_id(user_id)

    session = SessionData(session_id=session_id, user_id=user_id, data={})

    assert session.session_id == session_id
