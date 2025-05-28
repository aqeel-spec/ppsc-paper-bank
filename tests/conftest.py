# tests/conftest.py

import os
import sys
import pytest
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from httpx import AsyncClient, ASGITransport

# allow imports from project root
sys.path.append(str(Path(__file__).resolve().parents[1]))
load_dotenv()

from app.database import get_async_session, create_db_and_tables
from main import app

# ─── Configure test database engine & sessionmaker ─────────────────────────

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL or not TEST_DATABASE_URL.startswith("postgresql+asyncpg://"):
    raise RuntimeError(
        "Please set TEST_DATABASE_URL to an asyncpg URL in your .env"
    )

engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"ssl": True},
    execution_options={"compiled_cache": None},  # avoid cached-plan errors
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

# Override the FastAPI dependency so all routes use our test sessionmaker
async def _override_get_async_session():
    async with AsyncSessionLocal() as session:
        yield session

app.dependency_overrides[get_async_session] = _override_get_async_session

# ─── Prepare schema once per session ────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
async def prepare_database():
    # Drop & recreate all tables before any tests run
    await create_db_and_tables()
    yield
    # Dispose the engine after the session ends
    await engine.dispose()

# ─── Provide a raw AsyncSession for direct DB assertions ────────────────────

@pytest.fixture(scope="function")
async def async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

# ─── Provide an httpx AsyncClient against our FastAPI app ──────────────────

@pytest.fixture(scope="function")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
