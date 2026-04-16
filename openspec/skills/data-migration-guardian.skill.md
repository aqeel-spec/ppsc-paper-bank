# Skill: Data Migration Guardian

## Purpose

Guard schema evolution across SQLModel + Alembic.

## Process

1. Update SQLModel classes.
2. Create migration: `uv run alembic revision --autogenerate -m "..."`.
3. Review generated DDL for constraints/indexes/defaults.
4. Apply migration locally: `uv run alembic upgrade head`.
5. Validate read/write behavior via key routes.

## Rules

- Never rely solely on runtime `create_all` for production evolution.
- Keep migrations deterministic and reversible.
- Include any data backfill steps where needed.

## Done Criteria

- Migration applies cleanly.
- Runtime and API behavior match expected schema.
