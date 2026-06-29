from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=True)

Base = declarative_base()

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def connect_to_db() -> None:
    """Verify DB connectivity at startup (SQLAlchemy async engine)."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def disconnect_from_db() -> None:
    """Release the connection pool on shutdown."""
    await engine.dispose()
