# Data Acquisition Spec — Dawn (Playwright) + The News (RSS)

Purpose: define exactly what to pull from each source and in what shape, so this can be wrapped into an internal API. A second doc will cover how the app consumes that API + the RSS endpoint directly.

---

## Source 1: Dawn — Playwright scrape

**Why Playwright, not a simple fetch:** `www.dawn.com` returns bot-detection blocks on plain HTTP requests. A real browser context (Playwright) with standard headers/user-agent gets past this. `epaper.dawn.com` did NOT block a plain fetch, but served a cached/stale page — treat it as unreliable for "is today's paper live yet" checks unless you verify the date shown.

### Target pages to scrape
| Section | URL pattern | Use for |
|---|---|---|
| Opinion | `dawn.com/opinion` | Vocab source — editorial/opinion English is the CSS/PPSC-style register |
| Editorial | (listed within Opinion section) | Same as above |
| Latest News | `dawn.com/latest-news` | Current affairs feed |
| World | `dawn.com/world` | International current affairs |
| Pakistan | `dawn.com/pakistan` | National current affairs |
| Business | `dawn.com/business` | Economy-themed vocab/current affairs |
| Epaper (freshness check only) | `epaper.dawn.com` | Confirm today's edition is live before triggering the scrape run |

### Two-step scrape pattern
1. **Listing page** → get article links (title, URL, teaser, timestamp if shown)
2. **Article page** → open each link, extract:
   - Headline
   - Author (if opinion/editorial)
   - Publish date/time
   - Full body text (this is what gets fed to AI for vocab/summary extraction)
   - Category/section

### Freshness trigger logic
- Before running the full scrape, hit `epaper.dawn.com` and confirm the displayed date matches today
- If stale/mismatched, either retry after a delay or fall back to `dawn.com/latest-news` timestamp check instead
- Log scrape run with a timestamp so you can audit whether a given day's content was actually fresh

### Anti-bot practical notes (since you're already Playwright-based)
- Use a persistent browser context with a realistic user-agent
- Add small randomized delays between page navigations
- Avoid hammering all sections in parallel — sequential with delay is safer against rate-limiting/blocks
- Re-check bot-block status periodically; sites like Dawn can tighten detection over time

---

## Source 2: The News International — RSS

**Confirmed working feed (tested live):** `https://www.thenews.com.pk/rss/1/1` — National category, valid RSS 2.0, returns structured items.

### Feed structure (per item)
```xml
<item>
  <title>...</title>
  <link>...</link>
  <pubDate>...</pubDate>
  <guid>...</guid>
  <description><![CDATA[<img src="..."/> excerpt text...]]></description>
</item>
```

### Category feeds to pull (same pattern, different category ID)
- National — `/rss/1/1`
- World
- Business
- Sports (likely not needed for CSS/PPSC prep — skip)
- Entertainment (skip)

*(Category IDs beyond National need to be confirmed one-by-one — same URL pattern `/rss/1/{id}`, category IDs not yet verified for World/Business.)*

### ⚠️ Freshness caveat (found during testing)
The feed's `lastBuildDate` header showed a current date, but actual `<item>` entries inside were several months old at time of testing. **Do not trust the feed blindly** — always check each item's own `pubDate` against today's date before treating it as "new," and don't assume the feed refreshes same-day just because the header says so.

### Extraction per item
- Title
- Link (fetch full article text separately if the RSS excerpt isn't enough for AI extraction — RSS description is usually a short teaser only)
- pubDate
- Category (from which feed it came)

### Dawn CMS Publishing Architecture & Timestamps
- **Print Editions (Front Page, Opinion, Pakistan, Business):** Dawn publishes daily newspaper print editions in automated morning CMS releases (typically between 04:30 AM and 05:00 AM PKT). All articles belonging to that morning's print edition share the exact same CMS release timestamp (e.g., `04:40:34 AM PKT` / `2026-08-18T23:40:34.000Z`). This is Dawn's native CMS behavior, not an index/listing artifact.
- **Live / Breaking Updates (`updated_at`):** When articles receive rolling revisions, corrections, or breaking news updates during the day, Dawn updates `<time class="timestamp--time timeago">` and `JSON-LD dateModified`. The scraper extracts this into `updated_at`.
- **Carryover Stories:** Front pages occasionally feature older multi-day developing stories with earlier publication dates (e.g. from the previous day's CMS release).

---

## API Endpoint Query Parameters

`GET /api/newspapers` supports fine-grained control over payload size and UI asset requirements:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `source` | `all \| dawn \| thenews` | `all` | Source newspaper to query |
| `section` | `string` | `opinion` | Section (e.g. `front-page`, `opinion`, `world`, `business`, `pakistan`, `all`) |
| `date` | `string` | current date | Target publication date (`YYYY-MM-DD`) |
| `limit` | `number` | `10` | Maximum number of articles to return (1-200) |
| `full_body` | `boolean` | `true` | When `false`, returns short teaser excerpts instead of full body text |
| `include_audio` | `boolean` | `true` | When `false`, omits `audio_url` |
| `include_chunks` | `boolean` | `false` | When `true`, generates and attaches `audio_cues` word/sentence timing array for real-time player highlighting |
| `include_images` | `boolean` | `true` | When `false`, omits `image_url` |

---

## Unified Output Contract (for both sources)

Every scraped/pulled article normalizes into the same shape before hitting the downstream AI extraction step:

```json
{
  "source": "dawn | thenews",
  "section": "opinion | world | business | national | ...",
  "title": "string",
  "url": "string",
  "image_url": "string | null",
  "audio_url": "string | null",
  "audio_cues": [
    {
      "id": 1,
      "text": "WASHINGTON",
      "start_ms": 0,
      "end_ms": 650
    }
  ],
  "published_at": "ISO 8601 datetime",
  "updated_at": "ISO 8601 datetime | null",
  "scraped_at": "ISO 8601 datetime",
  "author": "string | null",
  "body_text": "string (full article text, Dawn; excerpt or fetched full text, The News)",
  "status": "fresh | stale | needs_review"
}
```

This is the payload your API should expose — one endpoint returning normalized articles per source/section/date, ready for the AI vocab/current-affairs extraction step downstream.

---

## Next Doc
Once this API is live, the second md will cover:
- API endpoint design (query by source/section/date)
- How the app pulls from this API + the raw RSS endpoint
- Trigger scheduling (tied to Dawn's publish time)
- Handoff into AI extraction (vocab schema, current-affairs summary schema)
