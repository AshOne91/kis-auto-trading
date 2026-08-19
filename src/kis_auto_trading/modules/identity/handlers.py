from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import (
    SessionData,
    SessionStore,
    create_session_id,
)
from kis_auto_trading.modules.identity.generated.models import LoginAccount
from kis_auto_trading.modules.identity.generated.schemas import (
    GetOperatorSessionResponse,
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
    ValidateSessionRequest,
    ValidateSessionResponse,
)
from kis_auto_trading.modules.identity.generated.sqlalchemy_repositories import (
    SQLAlchemyLoginAccountRepository,
)
from kis_auto_trading.modules.identity.passwords import (
    hash_password,
    verify_password,
)

IDENTITY_TARGET = ShardTarget(store="identity")
ACCOUNT_SHARD_COUNT = 2


async def signup(
    request: SignupRequest,
    session_registry: AsyncSessionRegistry,
) -> SignupResponse:
    email = request.email.strip().lower()
    async with session_registry.session(IDENTITY_TARGET) as session:
        repository = SQLAlchemyLoginAccountRepository(session)
        if await repository.find_by_email(email) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )
        user_id = uuid4()
        account = LoginAccount(
            user_id=user_id,
            email=email,
            password_hash=await asyncio.to_thread(hash_password, request.password),
            is_active=True,
            access_level="user",
            shard_id=_shard_id_for(user_id),
            created_at=datetime.now(UTC),
        )
        await repository.save(account)
    return SignupResponse(
        user_id=account.user_id,
        email=account.email,
        is_active=account.is_active,
    )


async def login(
    request: LoginRequest,
    session_store: SessionStore,
    session_registry: AsyncSessionRegistry,
) -> LoginResponse:
    email = request.email.strip().lower()
    async with session_registry.session(IDENTITY_TARGET) as session:
        repository = SQLAlchemyLoginAccountRepository(session)
        account = await repository.find_by_email(email)
    valid_password = account is not None and await asyncio.to_thread(
        verify_password,
        request.password,
        account.password_hash,
    )
    if account is None or not account.is_active or not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    access_token = create_session_id(str(account.user_id))
    await session_store.create(
        SessionData(
            session_id=access_token,
            user_id=str(account.user_id),
            data={
                "shard_id": account.shard_id,
                "access_level": account.access_level,
            },
        )
    )
    return LoginResponse(
        user_id=account.user_id,
        access_token=access_token,
        token_type="bearer",
    )


async def validate_session(
    request: ValidateSessionRequest,
    session_store: SessionStore,
) -> ValidateSessionResponse:
    session = await session_store.get(request.access_token)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )
    shard_id = session.data.get("shard_id")
    if not isinstance(shard_id, str):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session shard is missing",
        )
    return ValidateSessionResponse(
        user_id=UUID(session.user_id),
        shard_id=shard_id,
    )


async def get_operator_session(
    current_session: SessionData,
) -> GetOperatorSessionResponse:
    return GetOperatorSessionResponse(
        user_id=UUID(current_session.user_id),
        access_level="operator",
    )


def _shard_id_for(user_id: UUID) -> str:
    return str((user_id.int % ACCOUNT_SHARD_COUNT) + 1)
