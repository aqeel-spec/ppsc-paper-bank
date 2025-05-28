# tests/conftest.py

import os
import sys
import pytest
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.pool import StaticPool

from httpx import AsyncClient, ASGITransport

# allow imports from project root
sys.path.append(str(Path(__file__).resolve().parents[1]))
load_dotenv()

from app.database import get_async_session
from main import app

# Configure test database engine
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL or not TEST_DATABASE_URL.startswith("postgresql+asyncpg://"):
    raise RuntimeError(
        "Please set TEST_DATABASE_URL to an asyncpg URL in your .env"
    )

# Create test engine
engine = create_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"ssl": True},
    poolclass=StaticPool
)

# Override the FastAPI dependency
async def _override_get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session

app.dependency_overrides[get_async_session] = _override_get_async_session

# Prepare schema once per session
@pytest.fixture(scope="session", autouse=True)
async def prepare_database():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    # Cleanup after tests
    await engine.dispose()

# Provide AsyncSession for tests
@pytest.fixture(scope="function")
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session

# Provide AsyncClient for tests
@pytest.fixture(scope="function")
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
