"""Add normalized searchable content to canonical news records."""

import sqlalchemy as sa
from alembic import op

revision = "kis_automation_news_content_0001"
down_revision = "af_automation_durable_jobs_0001"
branch_labels = None
depends_on = "af_automation_news_0001"


def upgrade() -> None:
    op.add_column("news_articles", sa.Column("content", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("news_articles", "content")
