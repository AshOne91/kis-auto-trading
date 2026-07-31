from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.identity.generated.models import LoginAccount
from kis_auto_trading.modules.identity.generated.sqlalchemy_models import (
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
            created_at=record.created_at
        )
