from __future__ import annotations

import json
import logging
import os
import re
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response

LOGGER_NAME = "kis_auto_trading"
LOGGER = logging.getLogger(LOGGER_NAME)
_MANAGED_HANDLER = '_generated_observability_handler'
_URL_CREDENTIALS = re.compile(r'://([^:/\s]+):([^@/\s]+)@')
_SECRET_VALUE = re.compile(r'(?i)\b(password|token|secret|api[_-]?key)\s*([=:])\s*([^,\s]+)')


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            'timestamp': datetime.fromtimestamp(record.created, UTC).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': self._redact(record.getMessage()),
        }
        for field_name in (
            'request_id', 'method', 'path', 'status_code', 'duration_ms', 'event_id',
            'event_type', 'job_type', 'job_id', 'run_key', 'attempt', 'max_attempts'
        ):
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value
        if record.exc_info:
            payload['exception'] = self._redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def _redact(value: str) -> str:
        value = _URL_CREDENTIALS.sub(r'://\1:[REDACTED]@', value)
        return _SECRET_VALUE.sub(r'\1\2[REDACTED]', value)


def configure_logging() -> None:
    LOGGER.setLevel(os.getenv('LOG_LEVEL', 'INFO').upper())
    LOGGER.propagate = False
    for handler in list(LOGGER.handlers):
        if getattr(handler, _MANAGED_HANDLER, False):
            LOGGER.removeHandler(handler)
            handler.close()
    directory = Path(os.getenv('LOG_DIRECTORY', 'logs'))
    directory.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        directory / f'{LOGGER_NAME}-{socket.gethostname()}-{os.getpid()}.log',
        maxBytes=int(os.getenv('LOG_MAX_BYTES', str(10 * 1024 * 1024))),
        backupCount=int(os.getenv('LOG_BACKUP_COUNT', '7')),
        encoding='utf-8',
    )
    formatter = JsonFormatter()
    for handler in (logging.StreamHandler(), file_handler):
        handler.setFormatter(formatter)
        setattr(handler, _MANAGED_HANDLER, True)
        LOGGER.addHandler(handler)


def install_request_logging(app: FastAPI) -> None:
    @app.middleware('http')
    async def log_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = perf_counter()
        request_id = request.headers.get('X-Request-ID') or uuid4().hex
        fields = {
            'request_id': request_id,
            'method': request.method,
            'path': request.url.path,
        }
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception(
                'request failed',
                extra={
                    **fields,
                    'status_code': 500,
                    'duration_ms': round((perf_counter() - started_at) * 1000, 2),
                },
            )
            raise
        response.headers['X-Request-ID'] = request_id
        LOGGER.info(
            'request completed',
            extra={
                **fields,
                'status_code': response.status_code,
                'duration_ms': round((perf_counter() - started_at) * 1000, 2),
            },
        )
        return response
