# Daily News & Current Affairs System — Next.js Frontend Implementation Guide

This guide defines the complete frontend architecture, TypeScript data contracts, API endpoints, and interactive component specifications for integrating the **Daily Newspaper, Audio Sync Reader, and Current Affairs Exam Power Bank** into the **Next.js frontend**.

---

## 1. Feature Architecture Overview

```
                                ┌────────────────────────────────────────┐
                                │      Next.js App (/news Route)         │
                                └──────────────────┬─────────────────────┘
                                                   │
          ┌────────────────────────┬───────────────┴───────────────┬────────────────────────┐
          │                        │                               │                        │
 ┌────────┴────────┐      ┌────────┴────────┐             ┌────────┴────────┐      ┌────────┴────────┐
 │ Header & Nav    │      │ Interactive     │             │ Daily MCQs Quiz │      │ CSS Vocab Deck  │
 │ (TopBar Badge)  │      │ Audio Reader    │             │ Runner (Score)  │      │ (1-Click Import)│
 └────────┬────────┘      │ (Sync Karaoke)  │             └────────┬────────┘      └────────┬────────┘
          │               └────────┬────────┘                      │                        │
          │                        │                               │                        │
          └────────────────────────┼───────────────────────────────┴────────────────────────┘
                                   ▼
                 ┌───────────────────────────────────┐
                 │  FastAPI Backend (ppsc-paper-bank)│
                 │  + Flow API (NEW_API_URL:5000)    │
                 │  + Bedrock / GitHub Models LLM    │
                 └───────────────────────────────────┘
```

### Core Features for Next.js:
1. **Header & Navigation**: Integrated "Daily News & Current Affairs" badge in TopBar `/news`.
2. **Interactive Audio Reader**:
   - Streams native TTS `.mp3` directly (`audio_url`).
   - Real-time word-by-word karaoke-style text highlighting using `audio_cues` (`start_ms` / `end_ms`).
3. **AI Study Materials on Demand**:
   - **AI Exam Synopsis**: Core synopsis + bullet points + competitive exam angles.
   - **Daily MCQs**: Factual 4-option questions with explanations for PPSC/FPSC prep.
   - **High-Register Vocabulary**: Academic words with phonetic pronunciation, CSS definitions, synonyms, antonyms, and essay sentences.
   - **1-Click Import into Leitner Deck**: Directly imports extracted words into the user's personal spaced repetition box (`/api/news/vocab/import-to-deck`).
   - **CSS/PMS Point-of-View (PoV) Analysis**: Editorial outline with central thesis, key arguments, and policy recommendations.
4. **Current Affairs AI Mentor Chat**: Conversational AI Q&A with SQLite session memory for news debates.
5. **Theme System Compliance**: Fully compatible with the existing 11 color themes (`default_classic`, `ocean_blue`, `forest_green`, `sunrise_orange`, etc.).

---

## 2. API Endpoints Reference

Base Backend URL: `http://localhost:8000` (or your FastAPI proxy)

### A. Navigation & Statistics
| Endpoint | Method | Description |
|---|---|---|
| `/api/news/nav` | `GET` | Returns header title, name, URL (`/news`), badge, and sections list. |
| `/api/news/stats` | `GET` | Overall stats (`total_articles`, `today_articles`, `total_mcqs`, `total_vocab`, `section_breakdown`). |

### B. Ingestion & Collection
| Endpoint | Method | Query / Body Parameters | Description |
|---|---|---|---|
| `/api/news/collect` | `GET` / `POST` | `source=all\|dawn\|thenews`, `section=all\|opinion...`, `limit=10`, `include_audio=true`, `include_chunks=true` | Triggers news collection from `NEW_API_URL` (Flow API) and saves to database. |

### C. Article Feeds & Reader View
| Endpoint | Method | Query Parameters | Description |
|---|---|---|---|
| `/api/news/articles` | `GET` | `source`, `section`, `date_str` (`YYYY-MM-DD`), `search`, `limit=30`, `offset=0` | Paginated feed of stored articles. |
| `/api/news/articles/{id}` | `GET` | — | Returns full article details + `audio_cues` array + linked MCQs/Vocab/PoV. |

### D. AI Knowledge Generation
| Endpoint | Method | Query / Body | Description |
|---|---|---|---|
| `/api/news/articles/{id}/ai-summary` | `GET` / `POST` | — | Generates or fetches exam synopsis for the article. |
| `/api/news/articles/{id}/ai-mcqs` | `GET` / `POST` | `count=3` (1-10) | Generates factual 4-option MCQs and stores in DB. |
| `/api/news/articles/{id}/ai-vocab` | `GET` / `POST` | `count=4` (1-10) | Extracts high-register vocabulary words with CSS context. |
| `/api/news/articles/{id}/ai-pov` | `GET` / `POST` | — | Generates structured CSS/PMS Point-of-View analysis. |

### E. Quizzes, Vocab Deck & AI Mentor
| Endpoint | Method | Headers / Body | Description |
|---|---|---|---|
| `/api/news/mcqs` | `GET` | `date_str=YYYY-MM-DD`, `category`, `limit=50` | Retrieves daily current affairs MCQs. |
| `/api/news/vocab` | `GET` | `date_str=YYYY-MM-DD`, `word`, `limit=50` | Retrieves extracted vocabulary words. |
| `/api/news/vocab/import-to-deck` | `POST` | `Authorization: Bearer <token>`, `{"vocab_ids": ["..."], "box": 1}` | Imports news vocab directly into the user's Leitner deck (`words` table). |
| `/api/news/ai/chat` | `POST` | `{"message": "...", "article_id": "...", "session_id": "..."}` | Conversational Current Affairs mentor with memory. |

---

## 3. TypeScript Interfaces

```typescript
export interface AudioSyncCue {
  id: number;
  text: string;
  start_ms: number;
  end_ms: number;
}

export interface NewsArticle {
  id: string;
  source: 'dawn' | 'thenews';
  section: string;
  title: string;
  url: string;
  image_url?: string | null;
  audio_url?: string | null;
  audio_cues_json?: string | null;
  published_at: string;
  updated_at?: string | null;
  scraped_at: string;
  author?: string | null;
  body_text: string;
  summary?: string | null;
  status: 'fresh' | 'stale' | 'needs_review';
  is_current_affairs: boolean;
  created_at: string;
}

export interface NewsMCQ {
  id: string;
  article_id?: string | null;
  question: string;
  option_1: string;
  option_2: string;
  option_3: string;
  option_4: string;
  correct_index: number; // 0 to 3
  correct_answer: string;
  explanation?: string | null;
  category: string;
  difficulty: 'easy' | 'medium' | 'hard';
  target_date: string; // YYYY-MM-DD
  created_at: string;
}

export interface NewsVocab {
  id: string;
  article_id?: string | null;
  word: string;
  phonetic?: string | null;
  part_of_speech?: string | null;
  css_meaning: string;
  synonyms?: string | null;
  antonyms?: string | null;
  context_in_article?: string | null;
  css_usage_example?: string | null;
  target_date: string;
  created_at: string;
}

export interface NewsPoVAnalysis {
  id: string;
  article_id: string;
  article_title: string;
  author?: string | null;
  theme: string;
  relevant_papers_json?: string | null;
  central_thesis: string;
  key_arguments_json?: string | null;
  policy_recommendations_json?: string | null;
  created_at: string;
}

export interface NewsArticleDetailResponse {
  article: NewsArticle;
  audio_cues: AudioSyncCue[];
  mcqs: NewsMCQ[];
  vocabs: NewsVocab[];
  pov_analysis?: NewsPoVAnalysis | null;
}
```

---

## 4. Next.js Component Specifications

### 4.1 Page Route: `src/app/news/page.tsx`
Create the main news hub page with:
- **Header TopBar**: Displays news badge and navigation links.
- **Section Tabs**: All, Opinion & Editorial, Pakistan Affairs, World Geopolitics, Economy, Front Page, Latest.
- **Source Filter & Date Picker**: Dawn, The News, Date selector, Search input.
- **Trigger Button**: "Fetch Fresh News" (`POST /api/news/collect`).
- **Article Grid**: News cards showing source badge, reading time, audio indicator, title, and excerpt.

### 4.2 Audio Sync Reader Component: `src/components/news/AudioSyncReader.tsx`
Implements the real-time word-by-word highlighted playback:

```tsx
'use client';

import React, { useRef, useState, useEffect } from 'react';
import { AudioSyncCue, NewsArticle } from '@/types/news';

interface Props {
  article: NewsArticle;
  audioCues: AudioSyncCue[];
}

export const AudioSyncReader: React.FC<Props> = ({ article, audioCues }) => {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [activeCueId, setActiveCueId] = useState<number | null>(null);

  const handleTimeUpdate = () => {
    if (!audioRef.current || !audioCues.length) return;
    const currentMs = audioRef.current.currentTime * 1000;
    const currentCue = audioCues.find(
      (cue) => currentMs >= cue.start_ms && currentMs <= cue.end_ms
    );
    setActiveCueId(currentCue ? currentCue.id : null);
  };

  return (
    <div className="space-y-6">
      {/* Audio Player Bar */}
      {article.audio_url && (
        <div className="p-4 rounded-2xl bg-brand-50 border border-brand-100 flex items-center justify-between">
          <div>
            <h4 className="text-sm font-bold text-brand-900">Listen to Article</h4>
            <p className="text-xs text-brand-700">Native TTS with live word sync</p>
          </div>
          <audio
            ref={audioRef}
            src={article.audio_url}
            controls
            onTimeUpdate={handleTimeUpdate}
            className="w-72 h-10"
          />
        </div>
      )}

      {/* Article Body with Synchronized Highlighting */}
      <div className="text-lg leading-relaxed space-y-4">
        {audioCues.length > 0 ? (
          <div className="flex flex-wrap gap-x-1.5 gap-y-1">
            {audioCues.map((cue) => (
              <span
                key={cue.id}
                id={`cue-${cue.id}`}
                className={`transition-all duration-150 rounded px-0.5 ${
                  activeCueId === cue.id
                    ? 'bg-yellow-300 text-black font-bold shadow-sm'
                    : 'text-gray-800 dark:text-gray-200'
                }`}
              >
                {cue.text}
              </span>
            ))}
          </div>
        ) : (
          <p className="whitespace-pre-line text-gray-800 dark:text-gray-200">{article.body_text}</p>
        )}
      </div>
    </div>
  );
};
```

---

### 4.3 1-Click Vocab Import: `src/components/news/VocabImporter.tsx`

```tsx
'use client';

import React, { useState } from 'react';

export const importNewsVocabToDeck = async (vocabIds: string[], token: string) => {
  const res = await fetch('http://localhost:8000/api/news/vocab/import-to-deck', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      vocab_ids: vocabIds,
      box: 1,
      tags: 'Current Affairs, Newspaper Editorial',
    }),
  });

  if (!res.ok) {
    throw new Error('Failed to import vocabulary to deck');
  }
  return await res.json();
};
```

---

## 5. Summary Checklist for Frontend Devs

- [ ] Add `/news` route in Next.js app directory.
- [ ] Connect `GET /api/news/nav` to TopBar navigation.
- [ ] Render feed cards from `GET /api/news/articles`.
- [ ] Implement reader view with `AudioSyncReader` for word-by-word playback.
- [ ] Add action buttons for **AI Summary**, **Extract MCQs**, **Extract Vocab**, and **PoV Analysis**.
- [ ] Connect 1-click vocab addition to Leitner study deck using `POST /api/news/vocab/import-to-deck`.
- [ ] Implement interactive MCQ quiz runner from `GET /api/news/mcqs`.
