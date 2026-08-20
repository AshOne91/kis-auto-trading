"""AutoForge baseline for signal in automation."""

from alembic import op

revision = 'af_automation_signal_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE signal_events (\n    signal_id UUID PRIMARY KEY,\n    stock_code TEXT NOT NULL,\n    direction TEXT NOT NULL,\n    price TEXT NOT NULL,\n    confidence DOUBLE PRECISION NOT NULL,\n    observed_at TIMESTAMPTZ NOT NULL\n);')
    op.execute('CREATE INDEX ix_signal_events_stock_code ON signal_events (stock_code);')
    op.execute('CREATE INDEX ix_signal_events_observed_at ON signal_events (observed_at);')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS signal_events CASCADE')
