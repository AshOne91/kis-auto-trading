"""Project Signal subscriptions from account shards into automation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "kis_signal_projection_0001"
down_revision = "kis_automation_news_content_0001"
branch_labels = None
depends_on = "af_automation_signal_0001"


def upgrade() -> None:
    op.create_table(
        "signal_subscription_projections",
        sa.Column("subscription_id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("shard_id", sa.Text(), nullable=False),
        sa.Column("stock_code", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_signal_subscription_projections_user_id",
        "signal_subscription_projections",
        ["user_id"],
    )
    op.create_index(
        "ix_signal_subscription_projections_stock_code",
        "signal_subscription_projections",
        ["stock_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_signal_subscription_projections_stock_code",
        table_name="signal_subscription_projections",
    )
    op.drop_index(
        "ix_signal_subscription_projections_user_id",
        table_name="signal_subscription_projections",
    )
    op.drop_table("signal_subscription_projections")
