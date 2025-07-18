import logging
from typing import List
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from sqlmodel import Session, select
from app.database import engine
from app.models import MCQ, AnswerOption, Category
from app.routes.sessionDep import SessionDep

# configure a module-level logger
logger = logging.getLogger("scrape")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/scrape")


class ScrapeRequest(BaseModel):
    url:  str   # e.g. "https://testpoint.pk/paper-mcqs/5622/ppsc-all-mcqs-2025"
    slug: str   # must match Category.slug in DB


class ScrapeResponse(BaseModel):
    message: str


def crawl_pages(start_url: str) -> List[str]:
    """Follow rel="next" paginated links and return every page URL."""
    urls = []
    next_url = start_url
    headers = {"User-Agent": "MCQ-API/1.0"}

    logger.info(f"[crawl] starting at {start_url}")
    while True:
        logger.info(f"[crawl] queueing page: {next_url}")
        urls.append(next_url)
        resp = requests.get(next_url, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        nxt = soup.select_one('ul.pagination a.page-link[rel=next]')
        if not nxt:
            logger.info("[crawl] no more pages")
            break
        next_url = urljoin(start_url, nxt["href"])

    return urls


def extract_mcqs(soup: BeautifulSoup) -> List[dict]:
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

        opts = [li.get_text(strip=True) for li in items]
        correct_idx = next(
            (i for i, li in enumerate(items) if "correct" in (li.get("class") or [])),
            None
        )
        if correct_idx is None:
            continue

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
        })

    return out


def _scrape_and_insert_task(url: str, category_id: int):
    """
    Background task: crawl every page under `url`, parse MCQs,
    and insert them into the database under the given category_id.
    """
    try:
        pages = crawl_pages(url)
    except Exception as e:
        logger.error(f"[scrape] crawl failed: {e}")
        return

    inserted = 0
    with Session(engine) as session:
        for page_url in pages:
            logger.info(f"[scrape] fetching {page_url}")
            try:
                resp = requests.get(page_url, headers={"User-Agent": "MCQ-API/1.0"})
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"[scrape] failed to fetch {page_url}: {e}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            mcqs = extract_mcqs(soup)
            logger.info(f"[scrape] extracted {len(mcqs)} MCQs on this page")

            for mcq_data in mcqs:
                mcq = MCQ(**mcq_data, category_id=category_id)
                session.add(mcq)
                inserted += 1

        session.commit()
    logger.info(f"[scrape] done — inserted total {inserted} MCQs into category {category_id}")


@router.post(
    "/testpoint",
    response_model=ScrapeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_scrape(
    req: ScrapeRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
):
    # 1) Look up the Category row in the DB (or create it if missing)
    cat = session.exec(select(Category).where(Category.slug == req.slug)).one_or_none()
    if not cat:
        # auto-create the category record
        logger.info(f"[scrape] creating Category slug={req.slug!r}")
        cat = Category(slug=req.slug, name=req.slug.replace("_", " ").title())
        session.add(cat)
        session.commit()
        session.refresh(cat)

    # 2) Schedule the background task
    logger.info(f"[scrape] enqueueing task for category_id={cat.id}, url={req.url}")
    background_tasks.add_task(_scrape_and_insert_task, req.url, cat.id)

    return ScrapeResponse(message=f"Scraping of '{req.slug}' started")
