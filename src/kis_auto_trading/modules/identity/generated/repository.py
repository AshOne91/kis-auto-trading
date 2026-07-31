from typing import Protocol
from uuid import UUID

from kis_auto_trading.modules.identity.generated.models import LoginAccount


class LoginAccountRepository(Protocol):
    async def find_by_id(
        self, user_id: UUID,
    ) -> LoginAccount | None: ...
    async def save(
        self, aggregate: LoginAccount,
    ) -> None: ...
