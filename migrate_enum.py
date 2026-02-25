import sys
import os
from sqlalchemy import text

# Ensure the root directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine

def migrate_postgres_enum():
    """
    PostgreSQL natively validates Enums at the database level.
    Even though we added 'OPTION_E' to the Python Enum, the database ENUM type 'answeroption'
    was created strictly with ('OPTION_A', 'OPTION_B', 'OPTION_C', 'OPTION_D').
    
    This script safely appends the new value to the existing PG Enum type using AUTOCOMMIT
    so it doesn't fail under 'ALTER TYPE ADD VALUE cannot run inside a transaction block'.
    """
    if engine.dialect.name != "postgresql":
        print(f"Dialect is {engine.dialect.name}, skipping PG Enum migration.")
        return
        
    try:
        # We must execute this outside of a standard transaction block in PG
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("ALTER TYPE answeroption ADD VALUE IF NOT EXISTS 'OPTION_E';"))
            print("Successfully ensured 'OPTION_E' exists in the 'answeroption' PostgreSQL Enum TYPE!")
    except Exception as e:
        print(f"Error migrating enum: {e}")

if __name__ == "__main__":
    migrate_postgres_enum()
