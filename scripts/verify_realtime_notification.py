from __future__ import annotations

import argparse
import asyncio
import base64
import json
import secrets
import subprocess
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import uuid4

import websockets

DEFAULT_PROJECT_NAME = "kis_auto_trading-integration"
DEFAULT_PUBLIC_URL = "http://127.0.0.1:49400"


@dataclass(frozen=True, slots=True)
class SmokeConfiguration:
    project_name: str
    public_url: str
    shard_id: str
    timeout_seconds: float


def _arguments() -> SmokeConfiguration:
    parser = argparse.ArgumentParser(
        description="Verify one durable local realtime notification through Nginx."
    )
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument("--public-url", default=DEFAULT_PUBLIC_URL)
    parser.add_argument("--shard-id", default="1")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    arguments = parser.parse_args()
    if arguments.timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be positive")
    return SmokeConfiguration(
        project_name=arguments.project_name,
        public_url=arguments.public_url.rstrip("/"),
        shard_id=arguments.shard_id,
        timeout_seconds=arguments.timeout_seconds,
    )


def _docker(*arguments: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ("docker", *arguments),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=input_text,
        timeout=45,
    )
    if result.returncode:
        raise RuntimeError(
            f"Docker command failed: {arguments!r}\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def _container(project_name: str, service: str) -> str:
    containers = [
        value
        for value in _docker(
            "ps",
            "--filter",
            f"label=com.docker.compose.project={project_name}",
            "--filter",
            f"label=com.docker.compose.service={service}",
            "--format",
            "{{.ID}}",
        ).splitlines()
        if value
    ]
    if len(containers) != 1:
        raise RuntimeError(
            f"Expected one running {service!r} container for {project_name!r}, "
            f"got {containers!r}"
        )
    container = containers[0]
    health = _docker("inspect", "--format", "{{.State.Health.Status}}", container)
    if health.strip() != "healthy":
        raise RuntimeError(f"{service!r} container is not healthy: {health.strip()!r}")
    return container


def _session_id(user_id: str) -> str:
    routing_tag = base64.urlsafe_b64encode(user_id.encode("utf-8")).decode("ascii")
    return f"{routing_tag.rstrip('=')}.{secrets.token_urlsafe(32)}"


def _create_session(container: str, session_id: str, user_id: str, shard_id: str) -> None:
    source = f"""\
import asyncio
import os
from redis.asyncio import Redis
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.infrastructure.session_store.redis import RedisSessionStore

asyncio.run(
    RedisSessionStore(Redis.from_url(os.environ[\"REDIS_URL\"], decode_responses=True)).create(
        SessionData(
            {session_id!r},
            {user_id!r},
            {{\"access_level\": \"user\", \"shard_id\": {shard_id!r}}},
        )
    )
)
"""
    _docker("exec", "-i", container, "python", "-", input_text=source)


def _revoke_session(container: str, session_id: str) -> None:
    source = f"""\
import asyncio
import os
from redis.asyncio import Redis
from kis_auto_trading.infrastructure.session_store.redis import RedisSessionStore

asyncio.run(
    RedisSessionStore(Redis.from_url(os.environ[\"REDIS_URL\"], decode_responses=True)).revoke(
        {session_id!r}
    )
)
"""
    _docker("exec", "-i", container, "python", "-", input_text=source)


def _publish_delivery_intent(container: str, user_id: str, shard_id: str) -> None:
    source = f"""\
import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import aio_pika

from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.infrastructure.messaging.rabbitmq import RabbitMQPublisher
from kis_auto_trading.modules.signal.messaging import IN_APP_NOTIFICATION_ROUTING_KEY

async def main() -> None:
    intent_id = uuid4()
    message = EventMessage(
        event_type=\"signal.delivery-intent.created\",
        aggregate_id=str(intent_id),
        routing_key=IN_APP_NOTIFICATION_ROUTING_KEY,
        payload={{
            \"intent_id\": str(intent_id),
            \"signal_id\": str(uuid4()),
            \"subscription_id\": str(uuid4()),
            \"user_id\": {user_id!r},
            \"shard_id\": {shard_id!r},
            \"stock_code\": \"005930\",
            \"expires_at\": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            \"status\": \"pending\",
        }},
    )
    connection = await aio_pika.connect_robust(os.environ[\"RABBITMQ_URL\"])
    try:
        await RabbitMQPublisher(connection).publish(message)
    finally:
        await connection.close()

asyncio.run(main())
"""
    _docker("exec", "-i", container, "python", "-", input_text=source)


def _websocket_url(public_url: str) -> str:
    parsed = urlsplit(public_url)
    scheme = {"http": "ws", "https": "wss"}.get(parsed.scheme)
    if scheme is None or not parsed.netloc:
        raise ValueError("--public-url must be an absolute HTTP(S) URL")
    return urlunsplit((scheme, parsed.netloc, "/api/notifications/stream", "", ""))


def _notifications(public_url: str, session_id: str, timeout_seconds: float) -> list[dict[str, object]]:
    request = Request(
        f"{public_url}/api/notifications",
        headers={"Authorization": f"Bearer {session_id}"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        notifications = json.load(response)
    if not isinstance(notifications, list):
        raise TypeError("Notification response did not contain a list")
    return notifications


async def _verify(configuration: SmokeConfiguration) -> str:
    application = _container(configuration.project_name, "application")
    worker = _container(configuration.project_name, "message-worker")
    user_id = str(uuid4())
    session_id = _session_id(user_id)
    _create_session(application, session_id, user_id, configuration.shard_id)
    try:
        async with websockets.connect(
            _websocket_url(configuration.public_url),
            additional_headers={"Authorization": f"Bearer {session_id}"},
        ) as websocket:
            await websocket.send("smoke")
            _publish_delivery_intent(worker, user_id, configuration.shard_id)
            hint = json.loads(
                await asyncio.wait_for(
                    websocket.recv(), timeout=configuration.timeout_seconds
                )
            )
        if set(hint) != {"notification_id"} or not isinstance(
            hint["notification_id"], str
        ):
            raise RuntimeError(f"Unexpected realtime notification hint: {hint!r}")
        notification_id = hint["notification_id"]
        notifications = _notifications(
            configuration.public_url, session_id, configuration.timeout_seconds
        )
        if not any(item.get("notification_id") == notification_id for item in notifications):
            raise RuntimeError("Realtime hint did not have a durable notification record")
        return notification_id
    finally:
        _revoke_session(application, session_id)


def main() -> None:
    notification_id = asyncio.run(_verify(_arguments()))
    print(f"Realtime notification smoke verified: {notification_id}")


if __name__ == "__main__":
    main()
