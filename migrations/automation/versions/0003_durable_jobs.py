"""AutoForge durable jobs for automation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'af_automation_durable_jobs_0001'
down_revision = 'af_automation_outbox_0001'
branch_labels = ('automation_durable_jobs',)
depends_on = None


def upgrade() -> None:
    op.create_table(
        'durable_jobs',
        sa.Column('job_id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('job_type', sa.String(length=100), nullable=False),
        sa.Column('run_key', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('job_type', 'run_key', name='uq_durable_jobs_type_run_key'),
    )


def downgrade() -> None:
    op.drop_table('durable_jobs')
