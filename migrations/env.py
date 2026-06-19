from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_engine_url() -> str:
    return str(current_app.extensions["migrate"].db.engine.url).replace("%", "%%")


def get_metadata():
    return current_app.extensions["migrate"].db.metadata


def run_migrations_offline() -> None:
    url = get_engine_url()
    context.configure(
        url=url,
        target_metadata=get_metadata(),
        literal_binds=True,
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = current_app.extensions["migrate"].db.engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            compare_type=True,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
