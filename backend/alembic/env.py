from logging.config import fileConfig
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Import app config and models
import sys
from pathlib import Path

# Add the backend directory to the path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.core.db import Base
from app.core.models import User, Role, SubscriptionPlan, UserSubscription, Payment
from app.media.models import Video
from app.jobs.models import Job  # noqa: F401 — registers Job with Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 1. Get database URL from settings
database_url = settings.DATABASE_URL

# 2. ENSURE it is using asyncpg (Remove the old logic that was converting it to psycopg2)
if "postgresql://" in database_url and "+asyncpg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")

# 3. Set the database URL in the config
config.set_main_option("sqlalchemy.url", database_url)

# Set target_metadata for autogenerate support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


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


async def run_migrations_online() -> None:
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    # Use 'async with' instead of 'with'
    async with connectable.connect() as connection:
        # Use 'await connection.run_sync' to bridge the async connection to sync Alembic
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()

    with context.begin_transaction():
        context.run_migrations()