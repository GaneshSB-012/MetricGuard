import os
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# ============================================================
# Load .env BEFORE importing app modules.
#
# We use dotenv_values() + os.environ.setdefault() instead of
# load_dotenv() for maximum reliability — this guarantees the
# vars are in the process environment before app.database reads
# them, regardless of how Alembic was launched.
# ============================================================
from dotenv import dotenv_values

_project_root = Path(__file__).resolve().parent.parent
_env_file = _project_root / ".env"

if _env_file.exists():
    for key, value in dotenv_values(str(_env_file)).items():
        if value is not None:
            os.environ[key] = value

# Now it is safe to import the app's database config and models.
from app.database import DATABASE_URL, connect_args
from app.models import Base  # noqa: F401  — triggers model registration

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override the sqlalchemy.url with the value from our .env-based configuration
# so we never have to hard-code credentials in alembic.ini.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at the project's declarative Base metadata.
# This enables autogenerate to detect schema differences.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Build engine config from the .ini section, then override the URL.
    ini_section = config.get_section(config.config_ini_section, {})
    ini_section["sqlalchemy.url"] = DATABASE_URL

    connectable = engine_from_config(
        ini_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
