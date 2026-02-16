# Recent Updates (Last 3–5 Chats)

This document summarizes the latest backend changes around AI chat, streaming MCQ explanations, DB caching, roadmap generation, and the agent service.

## What Changed

### 1) Split responsibilities: Chat vs Stream

- **`POST /ai/chat`**
  - Purpose: **Main “everything” chat** (papers + tool-calling + MCQ browsing + DB search).
  - Supports tool calling via orchestrator-style tools (paper creation, scraping, study help, etc.).

- **`POST /ai/chat/stream`**
  - Purpose: **Streaming MCQ explanation only**.
  - Requires `mcq_id`.
  - Streams deltas (SSE) and caches the final answer in DB as `ai_explanation`.

### 2) DB caching: `ai_explanation`

- Added `ai_explanation` field to the MCQ table (`mcqs_bank`).
- Behavior:
  - On first stream for a given `mcq_id`: generates answer → **saves** to `ai_explanation`.
  - On subsequent requests: serves from DB and **streams cached text** (simulated typing), avoiding repeated LLM token usage.

### 3) New roadmap API

- **`POST /ai/roadmap`**
  - Returns a visual-friendly roadmap for PPSC preparation.
  - Output includes emoji + Mermaid diagram + “Animation Ideas” section.

### 4) Agent service runs “in parallel” with the main API

You can now use agent endpoints in the **same FastAPI process** (no need to run a separate server).

- **`GET /agent/health`**
- **`POST /agent/chat`**

This is equivalent to the standalone server in `agent_service.py`, but mounted as a router.

## API Reference

### A) Main chat: `POST /ai/chat`

**Purpose**: tool-calling chat (papers, scraping, MCQ browsing/search, study help).

**Body**

```json
{
  "question_text": "Create a 20-question paper for Computer Science, medium difficulty",
  "session_id": "u1",
  "use_internet": true
}
```

**Response (example)**

```json
{
  "session_id": "u1",
  "mode": "chat",
  "output": "..."
}
```

### B) Streaming MCQ explain: `POST /ai/chat/stream`

**Purpose**: stream MCQ explanation and cache it in DB.

**Body**

```json
{
  "mcq_id": 123,
  "session_id": "u1",
  "use_internet": true
}
```

**SSE Events**

- `meta` — `{ session_id, use_internet }`
- `status` — cache hit / save info
- `delta` — `{ delta: "..." }` streamed chunks
- `done` — `{ output, cached, saved_to_cache }`
- `error` — `{ message }`

**Notes**

- If `mcq_id` is missing, the endpoint returns an `error` event immediately.
- If cached text exists, it streams from cache and sets `cached: true`.

### C) Roadmap: `POST /ai/roadmap`

**Body**

```json
{
  "weeks": 8,
  "daily_hours": 2,
  "target": "PPSC",
  "subjects": ["GK", "English", "Computer"]
}
```

**Response**

```json
{
  "markdown": "..."
}
```

### D) Embedded agent service

#### `GET /agent/health`

Returns basic health + offline mode.

#### `POST /agent/chat`

**Body**

```json
{
  "query": "Make a paper for PMS English (20 MCQs)",
  "session_id": "u1",
  "metadata": {"client": "web"}
}
```

**Response**

```json
{
  "session_id": "u1",
  "answer": "..."
}
```

## Environment Variables

Optional tuning for cached streaming “typing” feel:

- `CACHE_STREAM_CHUNK` (default: `32`)
- `CACHE_STREAM_DELAY_MS` (default: `12`)

## Where the Changes Live

- AI endpoints, caching, stream logic, roadmap: app/routes/ai_chat.py
- DB column ensure/repair (including SQLite): app/database.py
- MCQ model field: app/models/mcqs_bank.py
- Embedded agent router: app/routes/agent_service.py
- Router registration: main.py

## Quick Smoke Test

1) Start the server.
2) Call streaming:
   - `POST /ai/chat/stream` with `{ "mcq_id": 123 }`
   - First run should say saved; second run should say cached.
3) Call agent:
   - `POST /agent/chat` with `{ "query": "List categories", "session_id": "u1" }`
4) Call roadmap:
   - `POST /ai/roadmap` with `{ "weeks": 8, "daily_hours": 2 }`
