"""Tests run against SQLite in memory — no Docker, no postgres, no vonk."""
import os

# Set before importing anything from app/: config and database read these at
# import time. Unconditional, so a DATABASE_URL in your shell can never point
# the suite at a real database.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ.setdefault("VONK_KEY", "test-key")
os.environ.setdefault("IMAGE_DIR", "/nonexistent-set-per-test")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401 — registers ORM tables
from app.database import Base, get_db, get_session_factory
from app.main import app


@pytest_asyncio.fixture
async def factory():
    """Session factory on a fresh in-memory database. One shared connection, so every
    session opened from it sees the same data."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(factory):
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(factory):
    """HTTP client with the DB dependency pointed at the test database, a new session per
    request as in production."""
    async def _get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def image_dir(tmp_path, monkeypatch):
    """Generated images go to a throwaway directory per test."""
    from app.config import settings

    monkeypatch.setattr(settings, "image_dir", str(tmp_path / "gen"))
    return tmp_path / "gen"
