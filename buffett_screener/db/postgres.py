"""
db/postgres.py — Async SQLAlchemy engine and session factory.
All pipeline writes go through AsyncSessionLocal.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings

engine = create_async_engine(
    settings.postgres_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,   # Auto-heal stale connections after macOS sleep
    echo=False,
)

AsyncSessionLocal: sessionmaker = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency-injection style session getter (used in FastAPI / tests)."""
    async with AsyncSessionLocal() as session:
        yield session
