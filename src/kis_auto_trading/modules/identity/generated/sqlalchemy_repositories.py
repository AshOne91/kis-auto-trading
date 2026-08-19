from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.identity.generated.models import (
    AccessLevelAudit,
    LoginAccount,
)
from kis_auto_trading.modules.identity.generated.sqlalchemy_models import (
    AccessLevelAuditRecord,
    LoginAccountRecord,
)


class SQLAlchemyLoginAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, user_id: UUID,
    ) -> LoginAccount | None:
        record = await self._session.get(
            LoginAccountRecord, user_id
        )
        if record is None:
            return None
        return LoginAccount(
            user_id=record.user_id,
            email=record.email,
            password_hash=record.password_hash,
            is_active=record.is_active,
            access_level=record.access_level,
            shard_id=record.shard_id,
            created_at=record.created_at
        )

    async def save(
        self, aggregate: LoginAccount,
    ) -> None:
        record = LoginAccountRecord(
            user_id=aggregate.user_id,
            email=aggregate.email,
            password_hash=aggregate.password_hash,
            is_active=aggregate.is_active,
            access_level=aggregate.access_level,
            shard_id=aggregate.shard_id,
            created_at=aggregate.created_at
        )
        await self._session.merge(record)

    async def find_by_email(
        self, email: str,
    ) -> LoginAccount | None:
        result = await self._session.execute(
            select(LoginAccountRecord).where(
                LoginAccountRecord.email == email
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return LoginAccount(
            user_id=record.user_id,
            email=record.email,
            password_hash=record.password_hash,
            is_active=record.is_active,
            access_level=record.access_level,
            shard_id=record.shard_id,
            created_at=record.created_at
        )


class SQLAlchemyAccessLevelAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, audit_id: UUID,
    ) -> AccessLevelAudit | None:
        record = await self._session.get(
            AccessLevelAuditRecord, audit_id
        )
        if record is None:
            return None
        return AccessLevelAudit(
            audit_id=record.audit_id,
            subject_user_id=record.subject_user_id,
            actor=record.actor,
            previous_access_level=record.previous_access_level,
            new_access_level=record.new_access_level,
            changed_at=record.changed_at
        )

    async def save(
        self, aggregate: AccessLevelAudit,
    ) -> None:
        record = AccessLevelAuditRecord(
            audit_id=aggregate.audit_id,
            subject_user_id=aggregate.subject_user_id,
            actor=aggregate.actor,
            previous_access_level=aggregate.previous_access_level,
            new_access_level=aggregate.new_access_level,
            changed_at=aggregate.changed_at
        )
        await self._session.merge(record)
