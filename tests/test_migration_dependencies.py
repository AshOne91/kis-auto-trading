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
