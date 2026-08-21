"""AutoForge baseline for market_history in automation."""

from alembic import op

revision = 'af_995f6cee244f28112f3fb0fb'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE domestic_daily_candles (\n    candle_id UUID PRIMARY KEY,\n    stock_code TEXT NOT NULL,\n    trading_date TEXT NOT NULL,\n    open_price TEXT NOT NULL,\n    high_price TEXT NOT NULL,\n    low_price TEXT NOT NULL,\n    close_price TEXT NOT NULL,\n    volume BIGINT NOT NULL\n);')
    op.execute('CREATE INDEX ix_domestic_daily_candles_stock_code ON domestic_daily_candles (stock_code);')
    op.execute('CREATE INDEX ix_domestic_daily_candles_trading_date ON domestic_daily_candles (trading_date);')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS domestic_daily_candles CASCADE')
