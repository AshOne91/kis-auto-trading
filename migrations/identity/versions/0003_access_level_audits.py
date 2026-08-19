"""Create immutable audit records for local access-level provisioning."""

import sqlalchemy as sa
from alembic import op

revision = "kis_identity_audit_0001"
down_revision = "kis_identity_access_level_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_level_audits",
        sa.Column("audit_id", sa.Uuid(), primary_key=True),
        sa.Column("subject_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("previous_access_level", sa.Text(), nullable=False),
        sa.Column("new_access_level", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("access_level_audits")
