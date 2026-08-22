"""AutoForge baseline for portfolio in account."""

from alembic import op

revision = 'af_account_portfolio_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE portfolio_snapshots (\n    snapshot_id UUID PRIMARY KEY,\n    connection_id UUID NOT NULL,\n    user_id UUID NOT NULL,\n    captured_at TIMESTAMPTZ NOT NULL,\n    position_count BIGINT NOT NULL\n);')
    op.execute('CREATE INDEX ix_portfolio_snapshots_connection_id ON portfolio_snapshots (connection_id);')
    op.execute('CREATE INDEX ix_portfolio_snapshots_user_id ON portfolio_snapshots (user_id);')
    op.execute('CREATE TABLE portfolio_position_snapshots (\n    position_id UUID PRIMARY KEY,\n    snapshot_id UUID NOT NULL,\n    user_id UUID NOT NULL,\n    stock_code TEXT NOT NULL,\n    product_name TEXT NOT NULL,\n    holding_quantity TEXT NOT NULL,\n    orderable_quantity TEXT NOT NULL,\n    current_price TEXT NOT NULL\n);')
    op.execute('CREATE INDEX ix_portfolio_position_snapshots_snapshot_id ON portfolio_position_snapshots (snapshot_id);')
    op.execute('CREATE INDEX ix_portfolio_position_snapshots_user_id ON portfolio_position_snapshots (user_id);')
    op.execute('CREATE INDEX ix_portfolio_position_snapshots_stock_code ON portfolio_position_snapshots (stock_code);')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS portfolio_position_snapshots CASCADE')
    op.execute('DROP TABLE IF EXISTS portfolio_snapshots CASCADE')
