"""AutoForge baseline for news in automation."""

from alembic import op

revision = 'af_automation_news_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE news_articles (\n    source_key TEXT PRIMARY KEY,\n    source_url TEXT NOT NULL,\n    provider TEXT NOT NULL,\n    title TEXT NOT NULL,\n    symbol TEXT NOT NULL,\n    published_at TIMESTAMPTZ,\n    publisher TEXT,\n    collected_at TIMESTAMPTZ NOT NULL\n);')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS news_articles CASCADE')
