from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from kis_auto_trading.infrastructure.access_control import AccessLevel
from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import SessionStore
from kis_auto_trading.modules.identity.generated.models import AccessLevelAudit
from kis_auto_trading.modules.identity.generated.sqlalchemy_repositories import (
    SQLAlchemyAccessLevelAuditRepository,
    SQLAlchemyLoginAccountRepository,
)

IDENTITY_TARGET = ShardTarget(store="identity")


@dataclass(frozen=True, slots=True)
class OperatorGrantResult:
    user_id: UUID
    changed: bool
    revoked_session_count: int


async def grant_operator_access(
    *,
    email: str,
    actor: str,
    session_registry: AsyncSessionRegistry,
    session_store: SessionStore,
) -> OperatorGrantResult:
    normalized_email = email.strip().lower()
    normalized_actor = actor.strip()
    if not normalized_email:
        raise ValueError("email must not be empty")
    if not normalized_actor:
        raise ValueError("actor must not be empty")

    changed = False
    async with session_registry.session(IDENTITY_TARGET) as session:
        account_repository = SQLAlchemyLoginAccountRepository(session)
        account = await account_repository.find_by_email(normalized_email)
        if account is None:
            raise LookupError("identity account was not found")
        if account.access_level == AccessLevel.USER.value:
            await account_repository.save(
                account.model_copy(
                    update={"access_level": AccessLevel.OPERATOR.value},
                )
            )
            audit_repository = SQLAlchemyAccessLevelAuditRepository(session)
            await audit_repository.save(
                AccessLevelAudit(
                    audit_id=uuid4(),
                    subject_user_id=account.user_id,
                    actor=normalized_actor,
                    previous_access_level=AccessLevel.USER.value,
                    new_access_level=AccessLevel.OPERATOR.value,
                    changed_at=datetime.now(UTC),
                )
            )
            changed = True
        elif account.access_level != AccessLevel.OPERATOR.value:
            raise ValueError("only user-to-operator access grants are supported")

    revoked_session_count = await session_store.revoke_user_sessions(
        str(account.user_id)
    )
    return OperatorGrantResult(
        user_id=account.user_id,
        changed=changed,
        revoked_session_count=revoked_session_count,
    )
