#!/usr/bin/env python3
"""
flush_db.py — wipe scraping / MCQ data from the database.

Usage:
    python flush_db.py                    # interactive (asks confirmation)
    python flush_db.py --yes              # skip confirmation prompt
    python flush_db.py --tables mcqs scraping   # only flush specific groups
    python flush_db.py --dry-run          # show what WOULD be deleted, do nothing

Table groups
------------
scraping  → scraping_states, top_bar, side_bar, website, websites
mcqs      → mcqs_bank, category
all       → both groups (default)

The schema (columns, indexes, FK constraints) is LEFT INTACT — only rows are removed.
Run `python main.py` / let the lifespan recreate tables afterwards if needed.
"""

import argparse
import sys
from pathlib import Path

# ── make sure the project root is on sys.path ─────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from app.database import engine  # reuses the same engine / URL as the FastAPI app


# ---------------------------------------------------------------------------
# Table groups (ordered to satisfy FK constraints — children before parents)
# ---------------------------------------------------------------------------

SCRAPING_TABLES = [
    "top_bar",
    "side_bar",
    "scraping_states",
    "website",
    "websites",
]

MCQ_TABLES = [
    "mcqs_bank",
    "category",
]

ALL_TABLES = SCRAPING_TABLES + MCQ_TABLES


def _count(conn, table: str) -> int:
    try:
        row = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return -1  # table may not exist yet


def _truncate_or_delete(conn, table: str, dialect: str, dry_run: bool) -> int:
    """Delete all rows from *table*. Returns row count before deletion."""
    before = _count(conn, table)
    if before == 0:
        print(f"  ⬜  {table:<30}  0 rows — skipping")
        return 0
    if before < 0:
        print(f"  ⚠️   {table:<30}  table not found — skipping")
        return 0

    if dry_run:
        print(f"  🔎  {table:<30}  would delete {before:,} rows  [DRY RUN]")
        return before

    try:
        if dialect in {"mysql", "mariadb"}:
            conn.execute(text(f"SET FOREIGN_KEY_CHECKS = 0"))
            conn.execute(text(f"TRUNCATE TABLE `{table}`"))
            conn.execute(text(f"SET FOREIGN_KEY_CHECKS = 1"))
        elif dialect == "postgresql":
            conn.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))
        elif dialect == "mssql":
            conn.execute(text(f"DELETE FROM [{table}]"))
            # TRUNCATE on MSSQL requires no FK refs; DELETE is safer
        else:
            # sqlite or unknown — plain DELETE
            conn.execute(text(f"DELETE FROM {table}"))

        print(f"  ✅  {table:<30}  {before:,} rows deleted")
        return before
    except Exception as exc:
        print(f"  ❌  {table:<30}  ERROR: {exc}")
        return 0


def flush(tables: list[str], dry_run: bool) -> None:
    dialect = engine.dialect.name
    print(f"\n🗄️  Database: {dialect.upper()}")
    print(f"{'[DRY RUN] ' if dry_run else ''}Flushing {len(tables)} table(s):\n")

    total_deleted = 0
    with engine.begin() as conn:
        for table in tables:
            total_deleted += _truncate_or_delete(conn, table, dialect, dry_run)

    verb = "would be" if dry_run else "were"
    print(f"\n{'🔎' if dry_run else '🗑️ '} Total rows that {verb} deleted: {total_deleted:,}")
    if not dry_run:
        print("✅ Flush complete. Schema is untouched.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flush (delete all rows from) scraping/MCQ tables."
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip the confirmation prompt.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what WOULD be deleted without actually deleting.",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        choices=["scraping", "mcqs", "all"],
        default=["all"],
        help="Which table groups to flush (default: all).",
    )
    args = parser.parse_args()

    # Resolve table list
    selected: list[str] = []
    for group in args.tables:
        if group == "scraping":
            selected += [t for t in SCRAPING_TABLES if t not in selected]
        elif group == "mcqs":
            selected += [t for t in MCQ_TABLES if t not in selected]
        else:  # "all"
            selected = ALL_TABLES[:]
            break

    print("=" * 55)
    print("⚠️   DATABASE FLUSH UTILITY")
    print("=" * 55)
    print("Tables to flush:")
    for t in selected:
        print(f"  • {t}")
    print()

    if args.dry_run:
        flush(selected, dry_run=True)
        return

    if not args.yes:
        answer = input("Type 'yes' to confirm deletion of ALL rows in the above tables: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(0)

    flush(selected, dry_run=False)


if __name__ == "__main__":
    main()
