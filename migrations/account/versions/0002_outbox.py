"""AutoForge transactional outbox for account."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'af_account_outbox_0001'
down_revision = None
branch_labels = ('account_outbox',)
depends_on = None


def upgrade() -> None:
    op.create_table(
        'outbox_events',
        sa.Column('event_id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('event_type', sa.String(200), nullable=False),
        sa.Column('event_version', sa.Integer(), nullable=False),
        sa.Column('aggregate_id', sa.String(200), nullable=False),
        sa.Column('routing_key', sa.String(200), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True)),
        sa.Column('last_error', sa.Text()),
    )
    op.create_index(
        'ix_outbox_pending', 'outbox_events', ['status', 'available_at']
    )
    op.create_table(
        'processed_messages',
        sa.Column('event_id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('processed_messages')
    op.drop_index('ix_outbox_pending', table_name='outbox_events')
    op.drop_table('outbox_events')
