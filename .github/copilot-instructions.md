# GitHub Copilot Repository Instructions

## Source of Truth

Use OpenSpec artifacts first:

- `openspec/backend-analysis.md`
- `openspec/openapi.json`
- `openspec/skills/*.skill.md`

## Backend Conventions

- Framework: FastAPI + SQLModel.
- Routes live in `app/routes/` and are mounted from `main.py`.
- Models live in `app/models/` and are imported in `app/models/__init__.py`.
- DB/session and dialect normalization are centralized in `app/database.py`.
- Auth/JWT is centralized in `app/security.py`.

## Change Rules

1. Preserve existing endpoint behavior and response models unless explicitly requested.
2. Keep route handlers thin; move heavy logic to service modules.
3. For schema changes, generate Alembic migrations.
4. If API surface changes, regenerate `openspec/openapi.json`.
5. Avoid introducing secrets/default credentials in code.

## Validation Checklist

- Run targeted tests for changed domains.
- Ensure imports/typing pass for changed files.
- Confirm router is included in `main.py` for any new route module.
