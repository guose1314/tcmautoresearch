from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine.url import make_url

from alembic import context
from src.infrastructure.alembic_runtime import resolve_alembic_database_target
from src.infrastructure.persistence import Base  # noqa: E402 — ORM metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def _resolve_sqlalchemy_url() -> str:
    resolved_target = resolve_alembic_database_target(
        config.get_main_option("sqlalchemy.url"),
        x_arguments=context.get_x_argument(as_dictionary=True),
        default_root_path=Path(__file__).resolve().parents[1],
    )
    config.set_main_option("sqlalchemy.url", resolved_target.sqlalchemy_url)

    alembic_logger = context.config.attributes.get("logger")
    if alembic_logger is None:
        import logging

        alembic_logger = logging.getLogger("alembic.env")

    sanitized_url = make_url(resolved_target.sqlalchemy_url).render_as_string(hide_password=True)
    alembic_logger.info(
        "Alembic database target resolved from %s: %s",
        resolved_target.source,
        sanitized_url,
    )
    return resolved_target.sqlalchemy_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = _resolve_sqlalchemy_url()
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
    _resolve_sqlalchemy_url()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
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
