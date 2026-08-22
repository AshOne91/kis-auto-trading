from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException, status

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisAccountConfigurationError,
    KisAccountCredentials,
)
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.infrastructure.outbox.repository import OutboxWriter
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)
from kis_auto_trading.modules.brokerage_account.generated.sqlalchemy_repositories import (
    SQLAlchemyBrokerageAccountConnectionRepository,
)

_CREDENTIAL_REF = "kis:default"
_PROVIDER = "kis"
_DISPLAY_NAME = "KIS default account"
_OWNER_ENV = "KIS_ACCOUNT_OWNER_USER_ID"


async def link_default_connection(
    current_session: SessionData,
    session_registry: AsyncSessionRegistry,
) -> BrokerageAccountConnection:
    user_id, target = _connection_location(current_session)
    credentials = _account_credentials()
    connection_id = _connection_id(user_id)
    account_mask = f"****{credentials.account_number[-4:]}"
    now = datetime.now(UTC)

    async with session_registry.session(target) as session:
        repository = SQLAlchemyBrokerageAccountConnectionRepository(session)
        existing = await repository.find_by_id(connection_id)
        if existing is not None and existing.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Brokerage account ownership conflicts",
            )
        if existing is not None and _matches_deployment(
            existing, credentials.environment, account_mask
        ):
            return existing

        connection = BrokerageAccountConnection(
            connection_id=connection_id,
            user_id=user_id,
            provider=_PROVIDER,
            environment=credentials.environment,
            display_name=_DISPLAY_NAME,
            account_mask=account_mask,
            credential_ref=_CREDENTIAL_REF,
            status="active",
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        await repository.save(connection)
        OutboxWriter(session).add(
            EventMessage(
                event_type="brokerage.account.connection-linked",
                aggregate_id=str(connection_id),
                routing_key="brokerage.account.connection-linked",
                payload={
                    "connection_id": str(connection_id),
                    "user_id": str(user_id),
                    "shard_id": target.shard_id or "",
                    "provider": _PROVIDER,
                    "status": connection.status,
                },
            )
        )
    return connection


async def get_connection(
    current_session: SessionData,
    session_registry: AsyncSessionRegistry,
) -> BrokerageAccountConnection:
    user_id, target = _connection_location(current_session)
    async with session_registry.session(target) as session:
        repository = SQLAlchemyBrokerageAccountConnectionRepository(session)
        connection = await repository.find_by_id(_connection_id(user_id))
    if connection is None or connection.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brokerage account connection was not found",
        )
    return connection


def _connection_location(session: SessionData) -> tuple[UUID, ShardTarget]:
    shard_id = session.data.get("shard_id")
    if not isinstance(shard_id, str) or not shard_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session shard is missing",
        )
    try:
        user_id = UUID(session.user_id)
        owner_user_id = UUID(os.environ[_OWNER_ENV])
    except (KeyError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KIS account owner is not configured",
        ) from error
    if user_id != owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="KIS account is not assigned to this user",
        )
    return user_id, ShardTarget(store="account", shard_id=shard_id)


def _account_credentials() -> KisAccountCredentials:
    try:
        return KisAccountCredentials.from_environment()
    except KisAccountConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KIS account credentials are not configured",
        ) from error


def _connection_id(user_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"autoforge:{user_id}:{_CREDENTIAL_REF}")


def _matches_deployment(
    connection: BrokerageAccountConnection,
    environment: str,
    account_mask: str,
) -> bool:
    return (
        connection.provider == _PROVIDER
        and connection.environment == environment
        and connection.display_name == _DISPLAY_NAME
        and connection.account_mask == account_mask
        and connection.credential_ref == _CREDENTIAL_REF
        and connection.status == "active"
    )
