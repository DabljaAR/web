from app.core.db import engine, Base
# Import all models so they're registered with Base.metadata
from app.core.models import User, Role  # noqa: F401
from app.core.video_model import Video  # noqa: F401 — stub for the Rust-owned videos table


async def init_db():
    """Initialize database by creating all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

