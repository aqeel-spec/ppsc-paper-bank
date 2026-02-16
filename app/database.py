# TH_BACK/apis/utils/db.py
from contextlib import asynccontextmanager
from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine
from fastapi import FastAPI
from app import settings
from dotenv import load_dotenv
import os
import sys
from urllib.parse import quote_plus, urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# Project root — used to resolve relative cert paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Import all models to ensure they are registered with SQLModel metadata
from app.models import *  # This ensures all table models are registered

load_dotenv()  # Load environment variables from .env file


# 1) Figure out which ENV we’re in (default to “production”)
env = os.getenv("ENV", "production").lower()


def _select_database_url(*, env_name: str) -> str | None:
    """Select DB URL based on environment + optional DB_PROFILE.

    Supports:
    - DB_PROFILE=local|azure|anything
    - DATABASE_URL_<PROFILE> (e.g. DATABASE_URL_LOCAL, DATABASE_URL_AZURE)
    - Falls back to DATABASE_URL
    - Test mode prefers TEST_DATABASE_URL
    """

    if env_name == "test":
        return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")

    profile = (os.getenv("DB_PROFILE") or "").strip().lower()
    if profile:
        prof_key = f"DATABASE_URL_{profile.upper()}"
        return os.getenv(prof_key) or os.getenv("DATABASE_URL")

    return os.getenv("DATABASE_URL")


def _jdbc_sqlserver_to_sqlalchemy_url(jdbc: str) -> str:
    """Convert jdbc:sqlserver://...;key=value;... to SQLAlchemy mssql+pyodbc URL.

    Requires `pyodbc` at runtime and ODBC driver installed on the machine.
    """
    prefix = "jdbc:sqlserver://"
    if not jdbc.lower().startswith(prefix):
        raise ValueError("Not a SQL Server JDBC URL")

    raw = jdbc[len(prefix) :]
    parts = [p for p in raw.split(";") if p]
    if not parts:
        raise ValueError("Invalid JDBC URL")

    server_part = parts[0]
    kv_parts = parts[1:]

    host = server_part
    port = 1433
    if ":" in server_part:
        host, port_str = server_part.split(":", 1)
        port_str = port_str.strip()
        if port_str.isdigit():
            port = int(port_str)

    props: dict[str, str] = {}
    for kv in kv_parts:
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        props[k.strip()] = v.strip()

    database = props.get("database") or props.get("Database")
    user = props.get("user") or props.get("User") or props.get("username")
    password = props.get("password") or props.get("Password")
    if password and password.startswith("{") and password.endswith("}"):
        password = password[1:-1]

    encrypt = (props.get("encrypt") or props.get("Encrypt") or "true").strip().lower()
    trust = (props.get("trustServerCertificate") or props.get("TrustServerCertificate") or "false").strip().lower()
    # These JDBC properties are optional and can cause driver-specific issues
    # in ODBC connection strings; we intentionally do not include them by default.
    # host_cert = props.get("hostNameInCertificate") or props.get("HostNameInCertificate")
    # timeout = props.get("loginTimeout") or props.get("LoginTimeout")
    authentication = (
        props.get("authentication")
        or props.get("Authentication")
        or props.get("auth")
        or props.get("Auth")
    )

    if not database:
        raise ValueError("JDBC URL missing 'database'")
    if not user:
        raise ValueError("JDBC URL missing 'user'")
    if password is None:
        raise ValueError("JDBC URL missing 'password'")

    driver = _resolve_mssql_odbc_driver()
    server = f"tcp:{host},{port}"

    odbc_parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={database}",
        f"UID={user}",
        f"PWD={password}",
        f"Encrypt={'yes' if encrypt in {'true','yes','1','on'} else 'no'}",
        f"TrustServerCertificate={'yes' if trust in {'true','yes','1','on'} else 'no'}",
    ]
    if authentication:
        odbc_parts.append(f"Authentication={authentication}")

    odbc_str = ";".join(odbc_parts) + ";"
    return "mssql+pyodbc:///?odbc_connect=" + quote_plus(odbc_str)


def _odbc_connection_string_to_sqlalchemy_url(odbc: str) -> str:
    """Wrap a raw ODBC connection string into a SQLAlchemy mssql+pyodbc URL.

    Supports either:
    - odbc:DRIVER={...};SERVER=...;DATABASE=...;UID=...;PWD=...;
    - DRIVER={...};SERVER=...;...

    If DRIVER isn't present, we inject a reasonable default.
    """

    raw = odbc.strip()
    if raw.lower().startswith("odbc:"):
        raw = raw[len("odbc:") :].strip()

    # If user didn't specify DRIVER=..., inject one.
    if "driver=" not in raw.lower():
        driver = _resolve_mssql_odbc_driver()
        raw = f"DRIVER={{{driver}}};" + raw.lstrip(";")

    # Ensure it ends with ';' (ODBC string convention)
    if not raw.endswith(";"):
        raw = raw + ";"

    return "mssql+pyodbc:///?odbc_connect=" + quote_plus(raw)


def _sqlsrv_dsn_to_odbc_connection_string(sqlsrv_dsn: str) -> str:
    """Convert a PHP-style sqlsrv DSN into an ODBC connection string.

    Accepts inputs like:
      - sqlsrv:server=tcp:host,1433;Database=mydb;UID=user;PWD=pass;Encrypt=yes;
      - sqlsrv:server=host,1433; database = mydb; user id = user; password = pass;

    Note: DRIVER is optional; if missing it will be injected later.
    """

    raw = sqlsrv_dsn.strip()
    if raw.lower().startswith("sqlsrv:"):
        raw = raw[len("sqlsrv:") :].strip()

    if not raw:
        raise ValueError("Invalid sqlsrv DSN")

    key_map = {
        "server": "SERVER",
        "data source": "SERVER",
        "address": "SERVER",
        "addr": "SERVER",
        "network address": "SERVER",
        "database": "DATABASE",
        "initial catalog": "DATABASE",
        "uid": "UID",
        "user": "UID",
        "user id": "UID",
        "userid": "UID",
        "username": "UID",
        "pwd": "PWD",
        "password": "PWD",
        "encrypt": "Encrypt",
        "trustservercertificate": "TrustServerCertificate",
        "authentication": "Authentication",
    }

    odbc_parts: list[str] = []
    server = None
    database = None

    for part in [p.strip() for p in raw.split(";") if p.strip()]:
        if "=" not in part:
            continue
        k_raw, v_raw = part.split("=", 1)
        k = k_raw.strip()
        v = v_raw.strip()
        if not k:
            continue

        k_lower = k.lower()
        canonical = key_map.get(k_lower, k)
        if canonical == "SERVER":
            server = v
        elif canonical == "DATABASE":
            database = v

        odbc_parts.append(f"{canonical}={v}")

    if not server:
        raise ValueError("sqlsrv DSN missing 'server'")
    if not database:
        raise ValueError("sqlsrv DSN missing 'database'")

    # Ensure SERVER and DATABASE are present even if user used unusual casing.
    # (If duplicates exist, ODBC will usually take the last one; that's fine.)
    if not any(p.upper().startswith("SERVER=") for p in odbc_parts):
        odbc_parts.insert(0, f"SERVER={server}")
    if not any(p.upper().startswith("DATABASE=") for p in odbc_parts):
        odbc_parts.insert(1, f"DATABASE={database}")

    return ";".join(odbc_parts) + ";"


def _normalize_database_url(db_url: str) -> str:
    """Normalize env DB URL to a SQLAlchemy engine URL.

    - jdbc:sqlserver://... => converted to mssql+pyodbc odbc_connect
    - odbc:DRIVER=...;SERVER=...;... => wrapped into mssql+pyodbc odbc_connect
    - raw ODBC strings containing SERVER=...;DATABASE=...;... => wrapped
    - everything else assumed to already be a SQLAlchemy URL
    """

    raw = db_url.strip()
    lower = raw.lower()

    if lower.startswith("jdbc:sqlserver://"):
        return _jdbc_sqlserver_to_sqlalchemy_url(raw)

    # Allow a PHP-like DSN (sqlsrv:server=...;Database=...;UID=...;PWD=...)
    if lower.startswith("sqlsrv:"):
        odbc = _sqlsrv_dsn_to_odbc_connection_string(raw)
        return _odbc_connection_string_to_sqlalchemy_url(odbc)

    if lower.startswith("odbc:"):
        return _odbc_connection_string_to_sqlalchemy_url(raw)

    # Heuristic: if it doesn't look like a URL, but looks like an ODBC string, wrap it.
    if "://" not in raw and ";" in raw and ("server=" in lower or "data source=" in lower):
        return _odbc_connection_string_to_sqlalchemy_url(raw)

    return raw


def _resolve_mssql_odbc_driver() -> str:
    """Choose an installed ODBC driver name for SQL Server.

    Priority:
    - If MSSQL_ODBC_DRIVER is set, require it to exist.
    - Else, pick the best available from common driver names.

    This avoids the common Windows error IM002 when the default
    (e.g. Driver 18) isn't installed yet.
    """

    requested = (os.getenv("MSSQL_ODBC_DRIVER") or "").strip()

    try:
        import pyodbc  # type: ignore

        installed = list(pyodbc.drivers())
    except Exception:
        installed = []

    if requested:
        if installed and requested not in installed:
            raise RuntimeError(
                "MSSQL_ODBC_DRIVER is set to '{req}', but it is not installed. "
                "Installed ODBC drivers: {drivers}. "
                "Install 'ODBC Driver 18 for SQL Server' (recommended) or set MSSQL_ODBC_DRIVER to an installed driver name.".format(
                    req=requested,
                    drivers=installed or "<unknown>",
                )
            )
        return requested

    preferred = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 13 for SQL Server",
        "ODBC Driver 11 for SQL Server",
        "SQL Server",
    ]

    for name in preferred:
        if name in installed:
            return name

    # Last resort: keep the previous default so error message points at driver.
    # If we have installed drivers, surface them.
    if installed:
        raise RuntimeError(
            "No supported SQL Server ODBC driver found. Installed ODBC drivers: {drivers}. "
            "Install 'ODBC Driver 18 for SQL Server' and retry.".format(drivers=installed)
        )

    return "ODBC Driver 18 for SQL Server"

# 2) Pick the right URL var (supports DB_PROFILE)
db_url = _select_database_url(env_name=env)

# 3) Bail if nothing is set
if not db_url:
    print(
        "❌ ERROR: DATABASE_URL is not defined in your environment",
        file=sys.stderr,
    )
    raise RuntimeError("DATABASE_URL is not defined")

# 4) Use it!
connection_string = _normalize_database_url(db_url)

active_profile = (os.getenv("DB_PROFILE") or "").strip().lower() or "default"
print(f"🗄️  DB_PROFILE: {active_profile}")

# 5) For logging: grab the scheme (e.g. “postgresql+asyncpg”) so we can uppercase it
db_scheme = connection_string.split("://", 1)[0].upper()

print(f"🔗 Connecting to : {db_scheme} database ")


def _build_mysql_connect_args(url: str) -> dict:
    """Extract ssl_ca from URL query and return connect_args with absolute path."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    args: dict = {}
    ssl_ca = qs.get("ssl_ca", [None])[0]
    if ssl_ca:
        ca_path = Path(ssl_ca)
        if not ca_path.is_absolute():
            ca_path = _PROJECT_ROOT / ca_path
        args["ssl_ca"] = str(ca_path)
        # Remove ssl_ca from the query string — it's now in connect_args
        qs.pop("ssl_ca", None)
        clean_query = urlencode(qs, doseq=True)
        parsed = parsed._replace(query=clean_query)
    return args, urlunparse(parsed)


# recycle connections after 5 minutes
# to correspond with the compute scale down
engine_kwargs: dict = {"pool_recycle": 300}

if connection_string.startswith("mysql"):
    connect_args, connection_string = _build_mysql_connect_args(connection_string)
    if connect_args:
        engine_kwargs["connect_args"] = connect_args
        print(f"🔒 MySQL SSL CA : {connect_args.get('ssl_ca', 'N/A')}")

engine = create_engine(connection_string, **engine_kwargs)


def ensure_ai_explanation_column() -> None:
    # SQLModel's create_all doesn't add columns to existing tables.
    # Add the column with a best-effort ALTER for supported DBs.
    with engine.begin() as conn:
        if engine.dialect.name == "mssql":
            conn.execute(
                text(
                    "IF COL_LENGTH('dbo.mcqs_bank','ai_explanation') IS NULL "
                    "BEGIN ALTER TABLE dbo.mcqs_bank ADD ai_explanation NVARCHAR(MAX) NULL END"
                )
            )
        elif engine.dialect.name in {"mysql", "mariadb"}:
            # MySQL: ignore if already exists.
            try:
                conn.execute(text("ALTER TABLE mcqs_bank ADD COLUMN ai_explanation LONGTEXT NULL"))
            except Exception:
                pass
        elif engine.dialect.name == "sqlite":
            # SQLite: ignore if already exists.
            try:
                conn.execute(text("ALTER TABLE mcqs_bank ADD COLUMN ai_explanation TEXT"))
            except Exception:
                pass



def get_engine():
    """Returns the database engine."""
    return engine

def get_session():
    with Session(engine) as session:
        yield session


def create_db_and_tables():
    """Creates the database tables."""
    try:
        SQLModel.metadata.create_all(engine)
        ensure_ai_explanation_column()
    except SQLAlchemyError as exc:
        # SQL Server cannot create indexes on NVARCHAR(MAX). If the category table
        # was previously created with an unbounded slug column, fix it and retry.
        msg = str(getattr(exc, "orig", exc))
        if (
            engine.dialect.name == "mssql"
            and "Column 'slug' in table 'category' is of a type that is invalid for use as a key column in an index" in msg
        ):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "IF COL_LENGTH('dbo.category','slug') IS NOT NULL "
                        "BEGIN ALTER TABLE dbo.category ALTER COLUMN slug NVARCHAR(255) NOT NULL END"
                    )
                )
            SQLModel.metadata.create_all(engine)
            ensure_ai_explanation_column()
            return

        raise
    
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
    auto_create = os.getenv("AUTO_CREATE_TABLES", "0") == "1"
    is_dev_like_env = env in {"dev", "development", "local", "test"}
    allow_start_without_db = os.getenv("ALLOW_START_WITHOUT_DB", "0") == "1"

    should_auto_create = auto_create or is_dev_like_env

    # Serverless note (Vercel): creating tables on every cold start is expensive
    # and can cause timeouts. Only do it when explicitly enabled.
    if should_auto_create:
        print("Creating tables…")
        try:
            create_db_and_tables()
            print("Tables created.")
        except SQLAlchemyError as exc:
            # Give a targeted hint for the most common misconfigurations.
            msg = str(getattr(exc, "orig", exc))
            if "Azure Active Directory only authentication is enabled" in msg:
                print(
                    "❌ Azure SQL rejected SQL login because 'Azure AD only authentication' is enabled. "
                    "Fix by either disabling AD-only on the Azure SQL Server, or switching DATABASE_URL_AZURE to AAD auth "
                    "(e.g. add authentication=ActiveDirectoryPassword and use an AAD user@domain.com)."
                )
            elif "10060" in msg or "Can't connect to MySQL server" in msg:
                print(
                    "❌ Cannot reach the MySQL server (timeout / error 10060). "
                    "Check: 1) Azure MySQL firewall allows your IP, "
                    "2) the server is running, 3) port 3306 is not blocked by VPN/firewall."
                )
            else:
                print(f"❌ DB connection error: {msg[:200]}")

            # In dev, allow the app to start without a DB so routes that don't
            # need DB still work.  In production, crash unless explicitly allowed.
            if is_dev_like_env or allow_start_without_db:
                print(
                    "⚠️  DB unavailable — starting anyway (ENV={env}). "
                    "Routes that need DB will fail until the connection is restored.".format(env=env)
                )
            else:
                raise
    else:
        print("Skipping table auto-create (AUTO_CREATE_TABLES!=1, ENV=production)")
        # Still ensure new columns exist for features that depend on them.
        try:
            ensure_ai_explanation_column()
        except Exception:
            # Don't hard-fail production startup for a best-effort column add.
            pass
    
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
