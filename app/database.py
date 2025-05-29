# TH_BACK/apis/utils/db.py
from contextlib import asynccontextmanager
from sqlmodel import Session, SQLModel, create_engine
from fastapi import FastAPI
from app import settings
from dotenv import load_dotenv
import os
import sys

load_dotenv()  # Load environment variables from .env file


# 1) Figure out which ENV we’re in (default to “production”)
env = os.getenv("ENV", "production").lower()

# 2) Pick the right URL var
if env == "test":
    db_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
else:
    db_url = os.getenv("DATABASE_URL")

# 3) Bail if nothing is set
if not db_url:
    print(
        "❌ ERROR: DATABASE_URL is not defined in your environment",
        file=sys.stderr,
    )
    raise RuntimeError("DATABASE_URL is not defined")

# 4) Use it!
connection_string = db_url

# 5) For logging: grab the scheme (e.g. “postgresql+asyncpg”) so we can uppercase it
db_scheme = connection_string.split("://", 1)[0].upper()

print(f"🔗 Connecting to : {db_scheme} database ")
    

# recycle connections after 5 minutes
# to correspond with the compute scale down
engine = create_engine(
    connection_string, pool_recycle=300
)



def get_engine():
    """Returns the database engine."""
    return engine

def get_session():
    with Session(engine) as session:
        yield session


def create_db_and_tables():
    """Creates the database tables."""
    SQLModel.metadata.create_all(engine)
    
    # drop all tables first (for dev)
    # SQLModel.metadata.drop_all(engine)
    # print("Dropping all tables…")
    # SQLModel.metadata.clear()
# from sqlalchemy import text
# def create_db_and_tables():
#     """
#     Drops all tables (and their associated composite types) in dependency order,
#     then recreates everything from SQLModel.metadata.
#     """
#     print("Dropping tables & types (with CASCADE)…")
#     with engine.begin() as conn:
#         # Drop tables in reverse-dependency order
#         conn.execute(text("DROP TABLE IF EXISTS paper_mcq CASCADE;"))
#         conn.execute(text("DROP TABLE IF EXISTS paper CASCADE;"))
#         conn.execute(text("DROP TABLE IF EXISTS mcq CASCADE;"))
#         conn.execute(text("DROP TABLE IF EXISTS category CASCADE;"))

#         # ALSO drop the leftover composite types that PostgreSQL created
#         conn.execute(text("DROP TYPE IF EXISTS paper_mcq CASCADE;"))
#         conn.execute(text("DROP TYPE IF EXISTS paper CASCADE;"))
#         conn.execute(text("DROP TYPE IF EXISTS mcq CASCADE;"))
#         conn.execute(text("DROP TYPE IF EXISTS category CASCADE;"))

#     print("Recreating tables…")
#     SQLModel.metadata.create_all(engine)
#     print("Tables created.")
    
 

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) Create tables at startup
    print("Creating tables…")
    create_db_and_tables()
    print("Tables created.")
    
    yield

    # # 2) Capture and store the running event loop on app.state
    # loop = asyncio.get_running_loop()
    # app.state.loop = loop
    # print("Event loop stored on app.state.loop:", loop)

    # yield  # app is now running

    # # 3) Teardown (optional): dispose the engine
    # print("Shutting down DB engine…")
    # await engine.dispose()
    # print("Engine shut down.")
