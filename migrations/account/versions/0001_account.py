"""AutoForge baseline for account in account."""

from alembic import op

revision = 'af_account_account_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE user_profiles (\n    user_id UUID PRIMARY KEY,\n    investment_experience TEXT NOT NULL,\n    risk_tolerance TEXT NOT NULL,\n    investment_goal TEXT NOT NULL,\n    monthly_budget DOUBLE PRECISION NOT NULL,\n    profile_completed BOOLEAN NOT NULL DEFAULT FALSE\n);')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS user_profiles CASCADE')
