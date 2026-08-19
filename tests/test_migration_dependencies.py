from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_news_content_migration_depends_on_news_baseline() -> None:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "migrations/automation")

    revision = ScriptDirectory.from_config(config).get_revision(
        "kis_automation_news_content_0001"
    )

    assert revision is not None
    assert revision.dependencies == "af_automation_news_0001"


def test_login_access_level_migration_follows_identity_baseline() -> None:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "migrations/identity")

    revision = ScriptDirectory.from_config(config).get_revision(
        "kis_identity_access_level_0001"
    )

    assert revision is not None
    assert revision.down_revision == "af_identity_identity_0001"


def test_identity_revision_ids_fit_alembic_version_column() -> None:
    revision = Path(
        "migrations/identity/versions/0003_access_level_audits.py"
    ).read_text(encoding="utf-8")
    revision_id = next(
        line.split("=", 1)[1].strip().strip('"')
        for line in revision.splitlines()
        if line.startswith("revision =")
    )
    assert len(revision_id) <= 32
