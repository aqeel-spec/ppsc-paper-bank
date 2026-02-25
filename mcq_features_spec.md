# MCQ Extended Features — Database & API Specification

## Overview
This document defines the data structures, API endpoints, and storage schemas required to support four new community-facing features of the MCQ system:

1. **Urdu Translations** — Store cached Urdu translations per MCQ
2. **Favorites** — Allow users to save MCQs to their personal list
3. **Community Discussions** — Per-MCQ message threads open to all users
4. **Submitted Answers** — Store user attempts with names and details for social learning

---

## 1. Urdu Translations Table

### Purpose
Cache Hugging Face translations so the same MCQ isn't re-translated on every visit.

### Schema: `mcq_translations`

| Column | Type | Description |
|---|---|---|
| `id` | `uuid` (PK) | Auto-generated |
| `mcq_id` | `varchar` | Foreign key to the MCQ record |
| `locale` | `varchar(10)` | Language code (e.g., `ur`, `hi`) |
| `translated_question` | `text` | Urdu translation of the question |
| `translated_options` | `jsonb` | `{ "A": "...", "B": "...", "C": "...", "D": "..." }` |
| `model_used` | `varchar` | e.g., `Helsinki-NLP/opus-mt-en-ur` |
| `created_at` | `timestamptz` | When translation was generated |
| `updated_at` | `timestamptz` | Last update |
| `is_verified` | `boolean` | Whether a human has verified the translation |
| `verified_by` | `varchar` | User ID of human verifier |

### API Endpoints

```http
GET  /api/mcqs/{mcq_id}/translation?locale=ur
POST /api/mcqs/{mcq_id}/translation          # Body: { locale, translated_question, translated_options }
```

### Caching Strategy
- Backend checks `mcq_translations` before calling Hugging Face
- If found and `updated_at` is < 30 days old → return cached
- If not found → call HF, store, return

---

## 2. Favorites Table

### Purpose
Let each user bookmark MCQs for later review. Displayed in the site header counter.

### Schema: `mcq_favorites`

| Column | Type | Description |
|---|---|---|
| `id` | `uuid` (PK) | Auto-generated |
| `user_id` | `varchar` | User identifier (FK to users table or anonymous session ID) |
| `mcq_id` | `varchar` | Foreign key to the MCQ |
| `category_slug` | `varchar` | Slug of the category the MCQ belongs to |
| `mcq_question_preview` | `text` | First 120 chars of the question for quick display |
| `created_at` | `timestamptz` | When it was saved |
| `notes` | `text` | Optional personal note the user added |

### Indexes
- `(user_id, mcq_id)` — unique to prevent duplicate favorites
- `(user_id)` — for fast lookup of all user favorites

### API Endpoints

```http
GET    /api/users/{user_id}/favorites            # Returns all MCQ favorites with details
POST   /api/users/{user_id}/favorites            # Body: { mcq_id, category_slug, mcq_question_preview }
DELETE /api/users/{user_id}/favorites/{mcq_id}   # Remove a favorite
GET    /api/users/{user_id}/favorites/count       # Returns { count: N }
```

### Response Example — `GET /favorites`
```json
{
  "count": 12,
  "items": [
    {
      "id": "uuid...",
      "mcq_id": "mcq-abc-123",
      "category_slug": "math-mcqs",
      "mcq_question_preview": "80% of 700 = ?",
      "created_at": "2025-02-25T14:00:00Z",
      "notes": "Review before exam"
    }
  ]
}
```

---

## 3. Community Discussions Table

### Purpose
Allow learners to post questions, corrections, or explanations under each MCQ for collaborative study.

### Schema: `mcq_discussions`

| Column | Type | Description |
|---|---|---|
| `id` | `uuid` (PK) | Auto-generated |
| `mcq_id` | `varchar` | Foreign key to the MCQ |
| `category_slug` | `varchar` | Category the MCQ belongs to |
| `parent_id` | `uuid` (nullable) | If this is a reply, reference parent message |
| `author_name` | `varchar(100)` | Display name of the poster |
| `author_email` | `varchar` | (Private, not shown to others) |
| `author_city` | `varchar` | Optional: city for social context |
| `body` | `text` | The message content (max 1500 chars) |
| `is_pinned` | `boolean` | Admin can pin important messages |
| `is_flagged` | `boolean` | Reported by users for moderation |
| `upvotes` | `integer` | Number of upvotes |
| `created_at` | `timestamptz` | Timestamp of submission |
| `updated_at` | `timestamptz` | If message was edited |
| `is_deleted` | `boolean` | Soft delete |

### Indexes
- `(mcq_id, created_at DESC)` — for paginated thread listing
- `(parent_id)` — for fetching reply threads

### API Endpoints

```http
GET  /api/mcqs/{mcq_id}/discussions?page=1&limit=10   # Paginated messages (newest first)
POST /api/mcqs/{mcq_id}/discussions                   # Submit a new message
PUT  /api/discussions/{discussion_id}/upvote           # Increment upvote
DELETE /api/discussions/{discussion_id}               # Soft delete (admin only)
```

### POST Request Body
```json
{
  "author_name": "Fatima Tariq",
  "author_email": "fatima@example.com",
  "author_city": "Lahore",
  "body": "I think option B is correct because...",
  "parent_id": null
}
```

### GET Response Example
```json
{
  "total": 8,
  "page": 1,
  "messages": [
    {
      "id": "uuid...",
      "author_name": "Fatima Tariq",
      "author_city": "Lahore",
      "body": "I believe the answer explanation is outdated...",
      "upvotes": 4,
      "is_pinned": false,
      "created_at": "2025-02-25T09:15:00Z",
      "replies": [
        {
          "id": "uuid...",
          "author_name": "Ahmad Khan",
          "author_city": "Karachi",
          "body": "Yes, you are right. The 2024 syllabus changed this.",
          "upvotes": 1,
          "created_at": "2025-02-25T10:00:00Z"
        }
      ]
    }
  ]
}
```

---

## 4. Submitted Answers Table

### Purpose
Store each user's selected option for an MCQ. Build a "community statistics" display (e.g., *"62% of learners chose B"*) and track individual performance history.

### Schema: `mcq_submissions`

| Column | Type | Description |
|---|---|---|
| `id` | `uuid` (PK) | Auto-generated |
| `mcq_id` | `varchar` | Foreign key to the MCQ |
| `category_slug` | `varchar` | Category slug |
| `submitter_name` | `varchar(100)` | Display name |
| `submitter_email` | `varchar` | Private, used to group attempts per user |
| `submitter_city` | `varchar` | Optional, for geo-interest maps |
| `selected_option` | `char(1)` | The option key selected: `A`, `B`, `C`, `D` |
| `is_correct` | `boolean` | Whether the selected option was correct |
| `time_taken_seconds` | `integer` | Seconds from MCQ view to submission |
| `submitted_at` | `timestamptz` | Timestamp |
| `session_id` | `varchar` | Anonymous session ID for grouping unauthenticated users |

### Indexes
- `(mcq_id, selected_option)` — for computing per-option distributions
- `(submitter_email, submitted_at DESC)` — for user history
- `(category_slug, submitted_at)` — for category-wide analytics

### API Endpoints

```http
POST /api/mcqs/{mcq_id}/submit                      # Submit an answer
GET  /api/mcqs/{mcq_id}/stats                        # Community answer distribution
GET  /api/users/{email}/history?page=1&limit=20      # User's answer history
```

### POST Request Body
```json
{
  "submitter_name": "Ahmad Khan",
  "submitter_email": "ahmad@example.com",
  "submitter_city": "Karachi",
  "selected_option": "B",
  "time_taken_seconds": 42,
  "session_id": "anon-session-xyz"
}
```

### GET Stats Response (Community Distribution)
```json
{
  "mcq_id": "mcq-abc-123",
  "total_attempts": 284,
  "correct_rate": 0.61,
  "distribution": {
    "A": { "count": 48, "percent": 16.9 },
    "B": { "count": 173, "percent": 60.9 },
    "C": { "count": 42, "percent": 14.8 },
    "D": { "count": 21, "percent": 7.4 }
  },
  "recent_submitters": [
    { "name": "Ahmad Khan", "city": "Karachi", "selected": "B", "is_correct": true },
    { "name": "Sana Ali", "city": "Lahore", "selected": "A", "is_correct": false }
  ]
}
```

---

## Frontend Display Plan

| Feature | Where Shown |
|---|---|
| Urdu Translation | Inline below each option (lazy-loaded on globe icon click) |
| Favorites Count | Site header heart icon with red badge counter |
| Favorites List | Future `/favorites` page |
| Discussion Count | Badge next to `💬` icon on each MCQ card |
| Discussion Thread | Opened in a modal on `💬` click |
| Community Stats | Shown after submitting an answer (pie or bar graphic) |
| Recent Submitters | Listed in the discussion modal or below answer reveal |

---

## Security & Privacy Notes

> [!IMPORTANT]
> - `author_email` and `submitter_email` must **never** be returned in public API responses. Strip before serializing.
> - Rate-limit `POST /discussions` to **5 per minute per IP** to prevent spam.
> - All `body` fields must be sanitized to prevent XSS injection before storage.
> - Add `is_deleted` soft-delete everywhere — never hard-delete community content.

---

## Suggested Implementation Order

1. `mcq_translations` — lowest risk, immediately improves UX and reduces HF API costs
2. `mcq_favorites` — simple CRUD, already used in frontend localStorage
3. `mcq_submissions` — valuable for analytics, non-blocking for users
4. `mcq_discussions` — most complex (threading, moderation), implement last
