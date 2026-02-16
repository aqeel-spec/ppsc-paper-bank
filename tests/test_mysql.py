"""Tests for MySQL (Azure Flexible Server) connectivity and SSL."""

import os
import pytest
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

# ---------------------------------------------------------------------------
# Skip the entire module when no MySQL DATABASE_URL is configured
# ---------------------------------------------------------------------------
_db_url = os.getenv("DATABASE_URL", "")
_is_mysql = _db_url.startswith("mysql")

pytestmark = pytest.mark.skipif(
    not _is_mysql,
    reason="DATABASE_URL is not a MySQL connection string — skipping MySQL tests",
)


class TestMySQLConnection:
    """Basic connectivity and SSL verification."""

    def test_engine_dialect_is_mysql(self):
        from app.database import engine

        assert engine.dialect.name == "mysql", (
            f"Expected mysql dialect, got {engine.dialect.name}"
        )

    def test_simple_select(self):
        from app.database import engine

        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == 1

    def test_ssl_is_active(self):
        """Verify the MySQL session is using SSL."""
        from app.database import engine

        with engine.connect() as conn:
            result = conn.execute(text("SHOW STATUS LIKE 'Ssl_cipher'"))
            row = result.fetchone()
            assert row is not None, "Ssl_cipher status variable not found"
            cipher = row[1]
            assert cipher, "SSL cipher is empty — connection is NOT encrypted"

    def test_current_database(self):
        from app.database import engine

        with engine.connect() as conn:
            result = conn.execute(text("SELECT DATABASE()"))
            db_name = result.scalar()
            assert db_name is not None
            print(f"Connected to database: {db_name}")

    def test_ssl_cert_file_exists(self):
        """Ensure the SSL CA cert referenced in DATABASE_URL actually exists."""
        project_root = Path(__file__).resolve().parent.parent
        cert_path = project_root / "cert" / "MysqlflexGlobalRootCA.crt.pem"
        assert cert_path.exists(), f"SSL CA cert not found at {cert_path}"


class TestMySQLTableCreation:
    """Verify SQLModel table creation on MySQL."""

    def test_create_tables(self):
        from app.database import create_db_and_tables

        # Should not raise
        create_db_and_tables()

    def test_tables_exist_after_creation(self):
        from app.database import engine

        with engine.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]
            assert len(tables) > 0, "No tables found after create_db_and_tables()"
            print(f"Tables found: {tables}")


class TestMySQLSession:
    """Verify the get_session dependency works."""

    def test_get_session_yields(self):
        from app.database import get_session

        gen = get_session()
        session = next(gen)
        assert session is not None
        # Clean up
        try:
            next(gen)
        except StopIteration:
            pass
