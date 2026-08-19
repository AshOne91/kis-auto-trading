from typing import Protocol
from uuid import UUID

from kis_auto_trading.modules.identity.generated.models import (
    AccessLevelAudit,
    LoginAccount,
)


class LoginAccountRepository(Protocol):
    async def find_by_id(
        self, user_id: UUID,
    ) -> LoginAccount | None: ...
    async def save(
        self, aggregate: LoginAccount,
    ) -> None: ...
    async def find_by_email(
        self, email: str,
    ) -> LoginAccount | None: ...


class AccessLevelAuditRepository(Protocol):
    async def find_by_id(
        self, audit_id: UUID,
    ) -> AccessLevelAudit | None: ...
    async def save(
        self, aggregate: AccessLevelAudit,
    ) -> None: ...
