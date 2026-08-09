from __future__ import annotations

import os

from alembic import command
from alembic.config import Config

DATABASE_TARGETS = [["identity", "IDENTITY_DATABASE_URL"], ["automation", "AUTOMATION_DATABASE_URL"], ["account", "ACCOUNT_SHARD_1_DATABASE_URL"], ["account", "ACCOUNT_SHARD_2_DATABASE_URL"]]


def migrate(store: str, environment_name: str) -> None:
    url = os.environ.get(environment_name)
    if not url:
        raise RuntimeError(
            f'Required environment variable is missing: {environment_name}'
        )
    config = Config('alembic.ini')
    config.set_main_option('script_location', f'migrations/{store}')
    config.set_main_option('sqlalchemy.url', url.replace('%', '%%'))
    command.upgrade(config, 'heads')


def main() -> None:
    for store, environment_name in DATABASE_TARGETS:
        migrate(store, environment_name)


if __name__ == '__main__':
    main()
