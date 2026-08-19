"""AutoForge baseline for market_data in automation."""

from alembic import op

revision = 'af_automation_market_data_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE market_price_snapshots (\n    snapshot_id UUID PRIMARY KEY,\n    stock_code TEXT NOT NULL,\n    current_price TEXT NOT NULL,\n    observed_at TIMESTAMPTZ NOT NULL\n);')
    op.execute('CREATE INDEX ix_market_price_snapshots_stock_code ON market_price_snapshots (stock_code);')
    op.execute('CREATE INDEX ix_market_price_snapshots_observed_at ON market_price_snapshots (observed_at);')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS market_price_snapshots CASCADE')
