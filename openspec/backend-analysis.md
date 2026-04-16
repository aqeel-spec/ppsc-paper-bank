# Backend OpenSpec Analysis

## Stack Snapshot

- Runtime: FastAPI app in `main.py`.
- ORM: SQLModel + SQLAlchemy engine/session in `app/database.py`.
- Migrations: Alembic configured with SQLModel metadata.
- Auth: JWT (`HS256`) + bcrypt in `app/security.py` and `app/routes/auth.py`.
- AI integrations: Chat, image generation, mock interview, and agent service routes.

## App Composition

Main application includes routers for:

- `/mcqs`, `/papers`, `/views`, `/categories`
- `/ai`, `/agent`, `/images`, `/bg`, `/interview`
- `/auth`, `/users`, `/mock-sessions`, `/daily-papers`
- `/suggestions`, `/admin`
- Additional route modules present: `/api/collector`, `/api/website-data`

CORS is currently open (`allow_origins=["*"]`) and should be environment-scoped in production.

## Domain Areas

1. MCQ bank and category hierarchy
2. Paper assembly, listing, HTML/PDF views
3. Scraping and website ingestion services
4. Authentication, user profile, admin moderation
5. Community feedback (discussion, favorites, submissions, translations)
6. Study sessions and daily papers
7. AI-assisted solving and interview simulation

## Data Model Surface

Large SQLModel set under `app/models/` includes:

- Core: `Category`, `MCQ`, `PaperModel`, `PaperMCQ`
- User/Auth: `User`, `UserSession`
- Community: discussion/favorite/submission/translation tables
- Learning/Session: mock sessions, daily papers, learning goals
- Interview: session/message/feedback/question scoring
- Website/scraping state + UI navigation entities

## Runtime and Configuration Observations

- DB URL resolution is profile-aware (`DB_PROFILE`, `DATABASE_URL_<PROFILE>` fallback chain).
- Multi-dialect DB handling exists (PostgreSQL, MySQL, SQLite, MSSQL normalization logic).
- Startup lifespan can auto-create tables based on environment flags.
- Security defaults include fallback secret/admin values that must be overridden in production.

## Risks and Priorities

1. Open CORS in production can expose authenticated endpoints.
2. Default `SECRET_KEY` and admin credentials are unsafe if env is misconfigured.
3. High route/module count suggests need for stricter API contract checks per release.
4. Some scraping and AI endpoints likely need stronger rate limiting and error budgets.

## OpenSpec Operating Rules

- Treat `openspec/openapi.json` as the API contract artifact.
- Any endpoint signature change requires OpenSpec refresh.
- Any schema/model change should be accompanied by Alembic migration.
- Prefer service-layer changes over route-level business logic expansion.

## Recommended Quality Gates

- API contract diff check on PR (OpenAPI JSON changed intentionally).
- Auth regression tests for token lifecycle and admin boundaries.
- Migration test for new SQLModel fields and enum changes.
- Smoke tests for key domains: MCQ CRUD, papers, auth, AI chat.
