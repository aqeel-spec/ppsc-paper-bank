#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from sqlmodel import SQLModel, Session, create_engine
from app.models.mcq import MCQ, AnswerOption  # ← your SQLModel MCQ class with explanation & category fields

# ──────────────────────────────────────────────────────────────────────────────
# scraper functions (exactly as before, minus the json.dump)
# ──────────────────────────────────────────────────────────────────────────────

BASE_LIST_URL = "https://testpoint.pk/past-papers-mcqs/ppsc-5-years-past-papers-subject-wise-(solved-with-details)"
HEADERS = {"User-Agent": "MCQ-DB-Seeder/1.0"}

def get_category_links():
    resp = requests.get(BASE_LIST_URL, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.select_one("table.section-hide-show")
    cats = []
    for a in table.select("tr td a[href]"):
        title = a.get_text(strip=True)
        href  = urljoin(BASE_LIST_URL, a["href"])
        slug  = re.sub(r'\W+', '_', title.lower().split("of")[-1]).strip('_')
        cats.append((slug, href))
    return cats

def crawl_pages(start_url):
    urls = []
    next_url = start_url
    while True:
        urls.append(next_url)
        resp = requests.get(next_url, headers=HEADERS); resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        nxt = soup.select_one('ul.pagination a.page-link[rel=next]')
        if not nxt: break
        next_url = urljoin(start_url, nxt["href"])
    return urls

def extract_mcqs(soup, category_slug):
    out = []
    container = soup.select_one("#content")
    if not container: return out

    for block in container.find_all("div", recursive=False):
        h5 = block.find("h5")
        if not (h5 and (qa := h5.find("a", class_="theme-color"))):
            continue

        ol = block.find("ol", {"type": "A"})
        if not ol: continue
        items = ol.find_all("li", recursive=False)
        if len(items) < 4: continue

        opts = [li.get_text(strip=True) for li in items]
        correct_idx = next((i for i,li in enumerate(items) if "correct" in li.get("class", [])), None)
        if correct_idx is None: continue

        expl_div = block.find("div", class_="question-explanation")
        explanation = expl_div.get_text(" ", strip=True) if expl_div else None

        out.append({
            "question_text":  qa.get_text(strip=True),
            "option_a":       opts[0],
            "option_b":       opts[1],
            "option_c":       opts[2],
            "option_d":       opts[3],
            "correct_answer": AnswerOption(f"option_{chr(ord('a') + correct_idx)}"),
            "explanation":    explanation,
            "category":       category_slug
        })
    return out

# ──────────────────────────────────────────────────────────────────────────────
# main: wire up to your database
# ──────────────────────────────────────────────────────────────────────────────

def main():
    # 1) spin up DB & tables
    engine = create_engine("sqlite:///./mcq.db", echo=False)
    SQLModel.metadata.create_all(engine)

    cats = get_category_links()
    print(f"→ Found {len(cats)} categories\n")

    total = 0
    with Session(engine) as session:
        for slug, url in cats:
            print(f"▶ Category «{slug}»")
            for page_url in crawl_pages(url):
                print(f"   • fetching {page_url}")
                r = requests.get(page_url, headers=HEADERS); r.raise_for_status()
                soup = BeautifulSoup(r.text, "lxml")
                page_mcqs = extract_mcqs(soup, slug)
                print(f"     → inserting {len(page_mcqs)} MCQs")
                for data in page_mcqs:
                    mcq = MCQ(**data)
                    session.add(mcq)
                session.commit()
                total += len(page_mcqs)

    print(f"\n✅ Done — {total} MCQs seeded into the database!")

if __name__ == "__main__":
    main()
