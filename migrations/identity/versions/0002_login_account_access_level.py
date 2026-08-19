"""Add the persisted access-level claim for login sessions."""

import sqlalchemy as sa
from alembic import op

revision = "kis_identity_access_level_0001"
down_revision = "af_identity_identity_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "login_accounts",
        sa.Column(
            "access_level",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("login_accounts", "access_level")
