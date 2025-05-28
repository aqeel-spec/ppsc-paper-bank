# app/database.py

import os
import asyncio
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# 1) Load your .env so DATABASE_URL is available
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# 2) Create an AsyncEngine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    connect_args={"ssl": True},                # if you need SSL
    execution_options={"compiled_cache": None}, # optional: disable prepared-statement cache
)

# 3) Make a sessionmaker for AsyncSession
async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI routes:
        async def foo(session: AsyncSession = Depends(get_async_session))
    """
    async with async_session_maker() as session:
        yield session

async def init_db() -> None:
    """
    Create all tables (and ENUM types) in the database.
    Must be called inside an async context (e.g. FastAPI lifespan).
    """
    # ensure all models are imported so SQLModel.metadata is populated
    import app.models.mcq  # <-- adjust to your actual module(s)

    async with engine.begin() as conn:
        # if you want to drop existing tables in dev uncomment:
        # await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

# Optional shutdown helper if you want to explicitly dispose
async def shutdown_db() -> None:
    await engine.dispose()

