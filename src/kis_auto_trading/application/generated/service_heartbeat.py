import asyncio
import json
import os
import re
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from urllib.request import Request, urlopen

from fastapi import FastAPI

from kis_auto_trading.application.observability import LOGGER

_ENDPOINT_ENV = 'CONTROL_PLANE_HEARTBEAT_URL'
_TOKEN_ENV = 'CONTROL_PLANE_API_TOKEN'
_SERVICE_NAME = 'kis_auto_trading'
_DEPLOYED_VERSION = '0.1.0'
_DEPENDENCIES = {'database': 'ok', 'session_store': 'ok'}
_INTERVAL_SECONDS = 30


@asynccontextmanager
async def service_heartbeat_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(
        run_service_heartbeat_reporter(),
        name='service-heartbeat-reporter',
    )
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def run_service_heartbeat_reporter(
    *,
    service_name: str = _SERVICE_NAME,
    dependencies: dict[str, str] = _DEPENDENCIES,
) -> None:
    endpoint = os.getenv(_ENDPOINT_ENV)
    token = os.getenv(_TOKEN_ENV)
    if not endpoint or not token:
        LOGGER.info('service heartbeat reporter disabled')
        return
    while True:
        try:
            await asyncio.to_thread(
                _post_heartbeat, endpoint, token, service_name, dependencies
            )
        except (OSError, ValueError) as error:
            LOGGER.warning(
                'service heartbeat report failed: %s', type(error).__name__
            )
        await asyncio.sleep(_INTERVAL_SECONDS)


def _post_heartbeat(
    endpoint: str, token: str, service_name: str, dependencies: dict[str, str]
) -> None:
    payload = {
        'instance_id': _instance_id(),
        'service_name': service_name,
        'deployed_version': _DEPLOYED_VERSION,
        'dependencies': dependencies,
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urlopen(request, timeout=5) as response:
        response.read()


def _instance_id() -> str:
    candidate = os.getenv('POD_NAME') or os.getenv('HOSTNAME') or socket.gethostname()
    normalized = re.sub(r'[^A-Za-z0-9._:-]', '-', candidate).strip('-')
    return normalized[:128] or 'unknown'
