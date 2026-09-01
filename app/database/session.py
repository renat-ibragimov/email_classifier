from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async DB session for a single request and close it on exit."""
    async with async_session() as session:
        # ASYNC119: FastAPI drives this generator to completion, so the context manager
        # always exits; this is the documented yield-dependency pattern.
        yield session  # noqa: ASYNC119
