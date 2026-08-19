# Vocabulary Learning System & AI Live Companion — Frontend Implementation Guide

This guide documents the complete frontend architecture, API integration contracts, and interactive component specs for the **PPSC Vocabulary Power Bank** (`ppsc_UI`), including the **Siri-Style Live Learner AI Globe**, **AI Explanations**, and **Quiz Results Persistence**.

---

## 1. Feature Architecture Overview

```
                               ┌────────────────────────────────────────┐
                               │       PPSC Vocab Learning Hub          │
                               └──────────────────┬─────────────────────┘
                                                  │
         ┌────────────────────────┬───────────────┴───────────────┬────────────────────────┐
         │                        │                               │                        │
┌────────┴────────┐      ┌────────┴────────┐             ┌────────┴────────┐      ┌────────┴────────┐
│  Study Deck     │      │ Vocab Library   │             │ Siri Live Globe │      │ Quiz & Analytics│
│  (Leitner 5-Box)│      │ (Search, Filter)│             │ (Voice Aura AI) │      │ (History/Score) │
└────────┬────────┘      └────────┬────────┘             └────────┬────────┘      └────────┬────────┘
         │                        │                               │                        │
         └────────────────────────┼───────────────────────────────┴────────────────────────┘
                                  ▼
                ┌───────────────────────────────────┐
                │  FastAPI Backend (ppsc-paper-bank)│
                │  + AWS Bedrock Mantle / Agents    │
                └───────────────────────────────────┘
```

### Core Features Implemented:
1. **User-Scoped Vocabulary Cards**: Private per user, rich fields (`word`, `meaning`, `relevant_meaning`, `sentence`, `hook`, `synonyms`, `antonyms`, `tags`).
2. **5-Box Leitner Spaced Repetition**: Dynamic intervals (`Box 1: 1d`, `Box 2: 3d`, `Box 3: 7d`, `Box 4: 14d`, `Box 5: 30d mastered`).
3. **Siri-Style Holographic Live AI Globe (`VocabAgenticGlobe`)**:
   - Continuous hands-free voice loop (Web Speech Recognition + Speech Synthesis).
   - Reactive soundwave audio equalizer.
   - Real-time deck awareness (Mastered count, Box 1 weak words, due reviews, active card).
   - Live oral quizzes and conversational exam mentoring.
4. **AI Explanations Persistence (`VocabAiExplanation`)**: Automatically stores AI explanations, mnemonics, and grammar tips.
5. **Quiz Results Persistence (`VocabQuizResult`)**: Tracks score, accuracy, question count, and voice mode usage.
6. **Themes & Study Methods**: 11 built-in themes, custom user theme creator, 6 pedagogical methods.
7. **Monthly Plan Calendar**: Heatmap activity visualization from `/api/plan`.

---

## 2. Authentication Contract

All requests require the logged-in user JWT bearer token:
```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

---

## 3. API Reference & Endpoints

### A. Siri-Style Live Learner AI Globe
* **Endpoint**: `POST /api/vocab/agent/chat` *(or Next.js proxy `/api/ai/vocab-globe`)*
* **Description**: Conversational AI tutor with real-time database context.

**Request Payload:**
```json
{
  "message": "Quiz me on my active deck with one question!",
  "card_id": "c4b38d92-1a2b-4e3f-9123-abcdef123456",
  "session_id": "vocab_globe_user_123",
  "voice_mode": true
}
```

**Response:**
```json
{
  "reply": "Let's do a live quiz! What is the primary meaning of 'abundant'? Is it A: Plentiful, B: Scarce, or C: Hidden? Speak your choice!",
  "session_id": "vocab_globe_user_123",
  "stats": {
    "total": 42,
    "mastered": 18,
    "box1": 6,
    "due_today": 4,
    "daily_target": 10
  }
}
```

---

### B. AI Vocabulary Explanations Persistence
* **Save Explanation**: `POST /api/vocab/ai-explanations`
* **Fetch History**: `GET /api/vocab/ai-explanations?word=ubiquitous&limit=20`

**Save Request Payload:**
```json
{
  "card_id": "c4b38d92-1a2b-4e3f-9123-abcdef123456",
  "word": "ubiquitous",
  "user_prompt": "Give a mnemonic hook and PPSC essay sentence.",
  "ai_response": "Mnemonic: 'You-be-everywhere'. Sentence: 'Digital smartphones have become ubiquitous in modern governance.'"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "user_id": "9780628e-3ef4-4f6b-8125-e103bb365b7a",
  "card_id": "c4b38d92-1a2b-4e3f-9123-abcdef123456",
  "word": "ubiquitous",
  "user_prompt": "Give a mnemonic hook and PPSC essay sentence.",
  "ai_response": "Mnemonic: 'You-be-everywhere'. Sentence: 'Digital smartphones have become ubiquitous in modern governance.'",
  "created_at": "2026-08-18T20:45:00Z"
}
```

---

### C. Vocabulary Quiz Results Persistence
* **Save Result**: `POST /api/vocab/quiz-results`
* **Fetch History**: `GET /api/vocab/quiz-results?limit=30`

**Save Request Payload:**
```json
{
  "total_questions": 10,
  "correct_count": 9,
  "accuracy": 90.0,
  "voice_used": true
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "user_id": "9780628e-3ef4-4f6b-8125-e103bb365b7a",
  "total_questions": 10,
  "correct_count": 9,
  "accuracy": 90.0,
  "voice_used": true,
  "created_at": "2026-08-18T20:46:00Z"
}
```

---

### D. Core Word & Deck Operations

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/words` | List user cards. Query filters: `due=true`, `date=YYYY-MM-DD`, `q=term`, `tag=essay` |
| `POST` | `/api/words` | Create a new vocabulary card |
| `PATCH` | `/api/words/{id}` | Action: `{"action": "grade", "correct": true, "recallSeconds": 5}` or `{"action": "complete"}` |
| `DELETE` | `/api/words/{id}` | Delete a card |
| `GET` | `/api/words/box-intervals` | Returns Leitner 5-box intervals and display labels |
| `GET` | `/api/words/methods` | Returns available study methods |
| `GET` | `/api/words/themes` | Returns builtin + custom themes |
| `POST` | `/api/words/themes/custom` | Create custom theme (`name`, `theme_config`) |
| `GET` | `/api/words/settings` | Get user study preferences |
| `PATCH` | `/api/words/settings` | Update `cards_per_day`, `selected_method`, `selected_theme`, `custom_card_fields` |
| `GET` | `/api/words/progress` | Get daily learning analytics history (`days=14`) |
| `GET` | `/api/plan?month=YYYY-MM` | Monthly calendar review heatmap data |

---

## 4. UI Component Architecture (`ppsc_UI`)

| Component | File Path | Responsibilities |
| :--- | :--- | :--- |
| **`VocabAgenticGlobe`** | `src/components/vocab/vocab-agentic-globe.tsx` | Holographic pulsing 3D globe, continuous hands-free voice loop, live discussion & stats context |
| **`VocabStudyDeck`** | `src/components/vocab/vocab-study-deck.tsx` | Flashcard flipping, Leitner grading (Correct/Wrong), timer, audio pronunciation, method selector |
| **`VocabLibrary`** | `src/components/vocab/vocab-library.tsx` | Search, tag filtering, box filters, bulk export, edit/delete actions |
| **`VocabQuizDialog`** | `src/components/vocab/vocab-quiz-dialog.tsx` | Timed multiple-choice quiz, voice input answers, score summary, saves to `/api/vocab/quiz-results` |
| **`VocabAiTutorDialog`** | `src/components/vocab/vocab-ai-tutor-dialog.tsx` | In-depth AI word explainer, mnemonic hooks, saves to `/api/vocab/ai-explanations` |
| **`VocabAnalytics`** | `src/components/vocab/vocab-analytics.tsx` | Retention curve, pace score, reviews done, box distribution chart |
| **`VocabCalendar`** | `src/components/vocab/vocab-calendar.tsx` | Heatmap calendar showing daily targets and review schedule |
| **`VocabThemeSelector`** | `src/components/vocab/vocab-theme-selector.tsx` | Card theme preview and custom color palette editor |
| **`VocabPdfExportDialog`**| `src/components/vocab/vocab-pdf-export-dialog.tsx`| Formats vocabulary into printable CSS/PPSC preparation cheat sheets |

---

## 5. Siri-Style Voice Interaction Implementation Details

### Continuous Hands-Free Listening Loop
```typescript
// Speech Recognition onend triggers next listening cycle automatically after TTS finishes
const speakVoice = (text: string) => {
  window.speechSynthesis.cancel();
  setAgentState("speaking");

  const cleanText = text.replace(/[*_#`[\]()]/g, "");
  const utterance = new SpeechSynthesisUtterance(cleanText);
  utterance.rate = 0.96;
  utterance.pitch = 1.05;

  utterance.onend = () => {
    setAgentState("idle");
    if (isContinuousVoiceRef.current && recognitionRef.current) {
      setTimeout(() => {
        try {
          recognitionRef.current.start();
          setAgentState("listening");
        } catch {}
      }, 350);
    }
  };

  window.speechSynthesis.speak(utterance);
};
```

---

## 6. Database Migrations Reference

Before launching UI features, ensure all Alembic migrations are applied:
1. `20260818_0004_add_vocab_extra_fields.py`
2. `20260818_0005_add_vocab_settings_theme_progress.py`
3. `20260818_0006_add_due_reminder_to_vocab_daily_progress.py`
4. `20260818_0007_add_vocab_ai_explanations_and_quiz_results.py` *(Creates `vocab_ai_explanations` & `vocab_quiz_results`)*

```bash
uv run alembic upgrade head
```

---

## 7. Automated Test Suite Verification

Run backend test verification:
```bash
# Unit tests for Vocab AI Explanations and Quiz Results (100% Passing)
uv run pytest tests/test_vocab_ai_and_quiz.py

# Full AWS Bedrock Models & Agent suite (5/5 Passing)
uv run python scripts/test_bedrock.py
```
