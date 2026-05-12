import subprocess

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database.session as session_module
from app.config import settings
from app.models.classification import ClassificationRecord  # noqa: F401  (register model)


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """Run alembic upgrade once per test session against test_db."""
    subprocess.run(["alembic", "upgrade", "head"], check=True)


@pytest_asyncio.fixture
async def db_session():
    """Per-test async DB session. Each test gets its own engine bound to its event loop.

    The FastAPI module-level engine and session factory are swapped to the test
    engine so requests routed through TestClient share the same connection pool.
    """
    engine = create_async_engine(settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    session_module.engine = engine
    session_module.async_session = sessionmaker

    async with sessionmaker() as session:
        await session.execute(text("TRUNCATE TABLE classification_record"))
        await session.commit()
        yield session
    await engine.dispose()
