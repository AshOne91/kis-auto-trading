"""AutoForge baseline for notification in account."""

from alembic import op

revision = 'af_account_notification_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE in_app_notifications (\n    notification_id UUID PRIMARY KEY,\n    delivery_intent_id UUID NOT NULL,\n    user_id UUID NOT NULL,\n    signal_id UUID NOT NULL,\n    stock_code TEXT NOT NULL,\n    created_at TIMESTAMPTZ NOT NULL,\n    read_at TIMESTAMPTZ\n);')
    op.execute('CREATE INDEX ix_in_app_notifications_delivery_intent_id ON in_app_notifications (delivery_intent_id);')
    op.execute('CREATE INDEX ix_in_app_notifications_user_id ON in_app_notifications (user_id);')
    op.execute('CREATE INDEX ix_in_app_notifications_signal_id ON in_app_notifications (signal_id);')
    op.execute('CREATE INDEX ix_in_app_notifications_stock_code ON in_app_notifications (stock_code);')
    op.execute('CREATE INDEX ix_in_app_notifications_created_at ON in_app_notifications (created_at);')
    op.execute('CREATE INDEX ix_in_app_notifications_read_at ON in_app_notifications (read_at);')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS in_app_notifications CASCADE')
