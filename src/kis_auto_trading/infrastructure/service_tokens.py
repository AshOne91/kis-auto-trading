from __future__ import annotations

import os
from collections.abc import Callable
from secrets import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException

SERVICE_TOKEN_ENVIRONMENTS = {
    'durable_jobs': 'DURABLE_JOB_API_TOKEN',
    'operator': 'OPERATOR_API_TOKEN',
}


def require_service_token(name: str) -> Callable[..., None]:
    token_env = SERVICE_TOKEN_ENVIRONMENTS[name]

    def require_token(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        expected_token = os.getenv(token_env)
        if not expected_token:
            raise HTTPException(status_code=503, detail='service API token is not configured')
        scheme, _, token = (authorization or '').partition(' ')
        if scheme != 'Bearer' or not compare_digest(token, expected_token):
            raise HTTPException(status_code=401, detail='invalid service API token')

    return require_token
