"""Alembic environment for QueryPilot AI database migrations.

This file configures Alembic to work with SQLAlchemy and the QueryPilot app database.
"""
import os
import sys
from logging.config import dictConfig

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import engine_from_config, pool
from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in a project.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    dictConfig(
        config.get_ini_option("logconfig") or {}
    )

# add your model's MetaData object here
# for 'autogenerate' support
from sqlalchemy import MetaData
target_metadata = MetaData()

# other values from the config, defined in the 'env.py' file in our project:
# - app_label: string, label of our application
# - version_locations: location of versions
# - version_table_schema: schema of the version table

# set targets interactively if not defined in alembic.ini
if not config.get_main_option("version_locations"):
    # auto-discover versions directory
    config.set_main_option(
        "version_locations",
        str(os.path.join(os.path.dirname(__file__), "versions")),
    )


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    In this scenario, we don't need a DB connection,
    just the URL.
    """
    url = os.getenv("APP_DATABASE_URL", "sqlite:///querypilot_app.db")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create a Engine
    and associate a connection with the context.
    """
    # Get database URL from environment
    url = os.getenv("APP_DATABASE_URL", "sqlite:///querypilot_app.db")

    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()