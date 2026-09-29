"""Alembic environment: resolve the DSN from application settings.

The migration engine intentionally uses the *sync* DSN
(:attr:`app.core.config.Settings.sync_database_url`) so Alembic works with plain
``asyncpg``/``psycopg2``/``pysqlite`` connections - the same URL used by
``init_sync_schema`` and the seed script.
"""

from __future__ import annotations

import app.models  # noqa: F401  ensure all model modules are imported
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.core.config import settings
from app.core.database import Base

config = context.config

target_metadata = Base.metadata


def _database_url() -> str:
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit:
        return explicit
    return settings.sync_database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
            # PostGIS objects are handled by init_sync_schema / baseline migration.
            include_object=lambda obj, name, type_, reflected, compare_to: True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()