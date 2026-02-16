"""
TestPoint.pk MCQ Extractor

Handles extraction of MCQs from TestPoint.pk website structure.
"""

import logging
from typing import List
from urllib.parse import urljoin
import time
from http.client import IncompleteRead

import requests
from bs4 import BeautifulSoup

from app.models import AnswerOption

logger = logging.getLogger("scrape")


def crawl_pages_testpoint(start_url: str) -> List[str]:
    """Follow rel="next" paginated links and return every page URL."""
    urls = []
    next_url = start_url
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    logger.info(f"[testpoint] starting at {start_url}")
    while True:
        logger.info(f"[testpoint] queueing page: {next_url}")
        urls.append(next_url)

        last_exc = None
        for attempt in range(1, 6):
            try:
                resp = requests.get(next_url, headers=headers, timeout=(10, 60))
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                break
            except (IncompleteRead, requests.exceptions.ChunkedEncodingError, requests.exceptions.RequestException) as e:
                last_exc = e
                if attempt < 5:
                    backoff_s = min(20.0, 1.5 * (2 ** (attempt - 1)))
                    logger.warning(f"[testpoint] transient fetch error (attempt {attempt}/5) for {next_url}: {e}; sleeping {backoff_s:.1f}s")
                    time.sleep(backoff_s)
                else:
                    raise

        nxt = soup.select_one('ul.pagination a.page-link[rel=next]')
        if not nxt:
            logger.info("[testpoint] no more pages")
            break
        next_url = urljoin(start_url, nxt["href"])

    return urls


def extract_mcqs_testpoint(soup: BeautifulSoup) -> List[dict]:
    """Extract MCQs from TestPoint.pk HTML structure."""
    out: List[dict] = []
    container = soup.select_one("#content")
    if not container:
        return out

    for block in container.find_all("div", recursive=False):
        h5 = block.find("h5")
        if not (h5 and (qa := h5.find("a", class_="theme-color"))):
            continue

        ol = block.find("ol", {"type": "A"})
        if not ol:
            continue
        items = ol.find_all("li", recursive=False)
        if len(items) < 4:
            continue

        # Extract all option texts (some questions have 5+ options)
        opts_all = [li.get_text(strip=True) for li in items]

        # Detect correct option index
        correct_idx = None
        for i, li in enumerate(items):
            classes = [c.lower() for c in (li.get("class") or [])]
            if any(c in ["correct", "right", "answer"] for c in classes):
                correct_idx = i
                break
        if correct_idx is None:
            continue

        # Explanation (plus: store additional options here when needed)
        expl_div = block.find("div", class_="question-explanation")
        explanation = expl_div.get_text(" ", strip=True) if expl_div else None

        # Map options into our fixed A-D schema.
        # If there are more than 4 options, we set D="Other" and keep the full original
        # D/E/F... options inside the explanation to avoid losing information.
        if len(opts_all) <= 4:
            option_a, option_b, option_c, option_d = opts_all[:4]
            if correct_idx == 0:
                correct_answer = AnswerOption.OPTION_A
            elif correct_idx == 1:
                correct_answer = AnswerOption.OPTION_B
            elif correct_idx == 2:
                correct_answer = AnswerOption.OPTION_C
            else:
                correct_answer = AnswerOption.OPTION_D
        else:
            option_a, option_b, option_c = opts_all[:3]
            option_d = "Other"

            # Build a markdown block with the original D/E/F... options
            extra_lines: List[str] = []
            if correct_idx >= 3:
                extra_lines.append(f"**Correct Answer:** {opts_all[correct_idx]}")
            extra_lines.append("Additional options:")
            for i in range(3, len(opts_all)):
                label = chr(ord('A') + i)
                extra_lines.append(f"{label}. {opts_all[i]}")

            extra_block = "\n".join(extra_lines)
            if explanation:
                explanation = f"{explanation}\n\n---\n{extra_block}"
            else:
                explanation = extra_block

            # Correct answer within A/B/C stays as-is; otherwise mark as D (Other)
            if correct_idx == 0:
                correct_answer = AnswerOption.OPTION_A
            elif correct_idx == 1:
                correct_answer = AnswerOption.OPTION_B
            elif correct_idx == 2:
                correct_answer = AnswerOption.OPTION_C
            else:
                correct_answer = AnswerOption.OPTION_D

        out.append({
            "question_text":  qa.get_text(strip=True),
            "option_a":       option_a,
            "option_b":       option_b,
            "option_c":       option_c,
            "option_d":       option_d,
            "correct_answer": correct_answer,
            "explanation":    explanation,
        })

    return out
