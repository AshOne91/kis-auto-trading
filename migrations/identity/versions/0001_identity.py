"""AutoForge baseline for identity in identity."""

from alembic import op

revision = 'af_identity_identity_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE login_accounts (\n    user_id UUID PRIMARY KEY,\n    email TEXT NOT NULL UNIQUE,\n    password_hash TEXT NOT NULL,\n    is_active BOOLEAN NOT NULL DEFAULT TRUE,\n    shard_id TEXT NOT NULL,\n    created_at TIMESTAMPTZ NOT NULL\n);')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS login_accounts CASCADE')
