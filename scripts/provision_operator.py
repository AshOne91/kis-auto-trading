"""Grant operator access through the local, user-owned Identity boundary."""

import argparse
import asyncio
import logging
import os

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.redis import RedisSessionStore
from kis_auto_trading.modules.identity.provisioning import grant_operator_access

LOGGER = logging.getLogger(__name__)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grant one existing local account operator access."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--actor", required=True)
    return parser.parse_args()


async def main(email: str, actor: str) -> None:
    identity_url = os.environ["IDENTITY_DATABASE_URL"]
    redis_url = os.environ["REDIS_URL"]
    engine = create_async_engine(identity_url, pool_pre_ping=True)
    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        result = await grant_operator_access(
            email=email,
            actor=actor,
            session_registry=AsyncSessionRegistry({"identity": engine}, {}),
            session_store=RedisSessionStore(client),
        )
    finally:
        await client.aclose()
        await engine.dispose()
    LOGGER.info(
        "operator access provisioned user_id=%s changed=%s revoked_sessions=%s",
        result.user_id,
        result.changed,
        result.revoked_session_count,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    arguments = _arguments()
    asyncio.run(main(arguments.email, arguments.actor))
