# app/database.py

import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    connect_args={"ssl": True},
)

# Create async session maker
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a SQLModel AsyncSession that auto-closes"""
    async with async_session_maker() as session:
        yield session

async def init_db() -> None:
    """Initialize the database, creating all tables"""
    # Import all models to ensure they're registered
    import app.models.mcq

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def shutdown_db() -> None:
    """Cleanup database connections"""
    await engine.dispose()

