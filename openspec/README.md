# OpenSpec Initialization

This folder contains backend analysis and executable API contract artifacts for this repository.

## What was initialized

- `openapi.json`: Generated from `main.app.openapi()`.
- `backend-analysis.md`: Architecture, domains, and risk map of the backend.
- `skills/`: Reusable implementation skills for AI IDE agents.

## Regenerate API spec

```bash
uv run python -c "import json, main; from pathlib import Path; Path('openspec').mkdir(exist_ok=True); Path('openspec/openapi.json').write_text(json.dumps(main.app.openapi(), indent=2), encoding='utf-8')"
```

## Suggested workflow

1. Update SQLModel models and route schemas.
2. Regenerate `openapi.json`.
3. Update `backend-analysis.md` if architecture changed.
4. Keep Copilot and Cursor instructions in sync with this folder.
