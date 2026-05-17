"""Alembic environment for Ecommerce."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from ecommerce.db.config import get_database_url
import ecommerce.db.models as _model_registration  # noqa: F401
from ecommerce.db.models.base import Base
from ecommerce.env import load_local_env_if_present

load_local_env_if_present()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importing ecommerce.db.models above loads every workflow-owned model module
# before Alembic reads Base.metadata.
target_metadata = Base.metadata


def _database_url() -> str:
    database_url = get_database_url()
    if database_url:
        return database_url
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    raise RuntimeError("ECOMMERCE_DATABASE_URL is not configured.")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
