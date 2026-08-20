"""Add a monotonic revision to Signal subscriptions."""

import sqlalchemy as sa
from alembic import op

revision = "kis_account_signal_revision_1"
down_revision = "af_account_outbox_0001"
branch_labels = None
depends_on = "af_account_signal_0001"


def upgrade() -> None:
    op.add_column(
        "signal_subscriptions",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("signal_subscriptions", "revision")
