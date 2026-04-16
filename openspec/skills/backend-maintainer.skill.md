# Skill: Backend Maintainer

## Purpose

Safely evolve FastAPI + SQLModel backend modules with minimal regressions.

## Inputs

- Target feature or bug
- Affected route(s), model(s), service(s)
- Relevant OpenSpec files

## Process

1. Locate route in `app/routes/` and corresponding model in `app/models/`.
2. Keep business logic in services where feasible.
3. Preserve response schemas and error semantics unless change is explicit.
4. If DB schema changes, add Alembic migration.
5. Regenerate `openspec/openapi.json` if endpoint contract changed.

## Done Criteria

- Endpoint behavior is verified.
- OpenAPI artifact is current.
- Migration path exists for model changes.
