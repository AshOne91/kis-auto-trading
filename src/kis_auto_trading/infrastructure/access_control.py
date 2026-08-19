from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status

from .session_store.protocol import SessionData
from .session_store.provider import get_current_session


class AccessLevel(StrEnum):
    USER = 'user'
    OPERATOR = 'operator'
    DEVELOPER = 'developer'
    ADMINISTRATOR = 'administrator'


ACCESS_LEVEL_RANK = {
    AccessLevel.USER: 10,
    AccessLevel.OPERATOR: 20,
    AccessLevel.DEVELOPER: 30,
    AccessLevel.ADMINISTRATOR: 40,
}


def require_access_level(required: AccessLevel) -> Callable[..., None]:
    required_level = AccessLevel(required)

    async def require_human_access(
        current_session: Annotated[
            SessionData, Depends(get_current_session)
        ],
    ) -> None:
        raw_access_level = current_session.data.get('access_level')
        try:
            actual_level = AccessLevel(raw_access_level)
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='session access level is invalid',
            ) from error
        if ACCESS_LEVEL_RANK[actual_level] < ACCESS_LEVEL_RANK[required_level]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='insufficient access level',
            )

    return require_human_access
