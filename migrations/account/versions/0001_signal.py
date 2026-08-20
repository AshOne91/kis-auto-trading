"""AutoForge baseline for signal in account."""

from alembic import op

revision = 'af_account_signal_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE signal_subscriptions (\n    subscription_id UUID PRIMARY KEY,\n    user_id UUID NOT NULL,\n    stock_code TEXT NOT NULL,\n    enabled BOOLEAN NOT NULL DEFAULT TRUE\n);')
    op.execute('CREATE INDEX ix_signal_subscriptions_user_id ON signal_subscriptions (user_id);')
    op.execute('CREATE INDEX ix_signal_subscriptions_stock_code ON signal_subscriptions (stock_code);')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS signal_subscriptions CASCADE')
