"""AutoForge baseline for brokerage_account in account."""

from alembic import op

revision = 'af_0f60163b2ebcbec8aa8039df'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE brokerage_account_connections (\n    connection_id UUID PRIMARY KEY,\n    user_id UUID NOT NULL,\n    provider TEXT NOT NULL,\n    environment TEXT NOT NULL,\n    display_name TEXT NOT NULL,\n    account_mask TEXT NOT NULL,\n    credential_ref TEXT NOT NULL,\n    status TEXT NOT NULL,\n    created_at TIMESTAMPTZ NOT NULL,\n    updated_at TIMESTAMPTZ NOT NULL\n);')
    op.execute('CREATE INDEX ix_brokerage_account_connections_user_id ON brokerage_account_connections (user_id);')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS brokerage_account_connections CASCADE')
