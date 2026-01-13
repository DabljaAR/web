from app.core.db import engine, Base
# Import all models so they're registered with Base.metadata
from app.core.models import User, Role # noqa: F401


async def init_db():
    """Initialize database by creating all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

