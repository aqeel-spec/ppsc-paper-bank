# Skill: API Contract Enforcer

## Purpose

Ensure code changes remain consistent with documented FastAPI contract.

## Process

1. Run OpenAPI regeneration command.
2. Compare changed paths/operations/schemas.
3. Verify breaking changes are intentional and documented.
4. Confirm router registration still exists in `main.py`.

## Checks

- Path parameters and body models unchanged unless expected.
- Auth-protected endpoints still require proper dependencies.
- Response models are explicit for public APIs.

## Done Criteria

- Contract drift is explained and accepted.
- `openspec/openapi.json` reflects current app state.
