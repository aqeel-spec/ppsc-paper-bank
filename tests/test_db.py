import logging
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine

logging.basicConfig(level=logging.INFO)

def test_db():
    try:
        with engine.connect() as conn:
            print("Successfully connected to the PostgreSQL database!")
    except Exception as e:
        print(f"Failed to connect: {e}")

if __name__ == "__main__":
    test_db()
