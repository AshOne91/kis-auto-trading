"""AutoForge additive migration: signal_delivery_intent."""

from alembic import op

revision = 'af_automation_signal_0002_signal_delivery_intent'
down_revision = 'af_automation_signal_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE signal_delivery_intents (\n    intent_id UUID PRIMARY KEY,\n    signal_id UUID NOT NULL,\n    subscription_id UUID NOT NULL,\n    user_id UUID NOT NULL,\n    shard_id TEXT NOT NULL,\n    stock_code TEXT NOT NULL,\n    expires_at TIMESTAMPTZ NOT NULL,\n    status TEXT NOT NULL DEFAULT 'pending'\n);")
    op.execute('CREATE INDEX ix_signal_delivery_intents_signal_id ON signal_delivery_intents (signal_id);')
    op.execute('CREATE INDEX ix_signal_delivery_intents_subscription_id ON signal_delivery_intents (subscription_id);')
    op.execute('CREATE INDEX ix_signal_delivery_intents_user_id ON signal_delivery_intents (user_id);')
    op.execute('CREATE INDEX ix_signal_delivery_intents_stock_code ON signal_delivery_intents (stock_code);')
    op.execute('CREATE INDEX ix_signal_delivery_intents_expires_at ON signal_delivery_intents (expires_at);')
    op.execute('ALTER TABLE signal_events ADD COLUMN expires_at TIMESTAMPTZ')
    op.execute('CREATE INDEX ix_signal_events_expires_at ON signal_events (expires_at)')


def downgrade() -> None:
    op.execute('ALTER TABLE signal_events DROP COLUMN expires_at')
    op.execute('DROP TABLE IF EXISTS signal_delivery_intents CASCADE')
