import logging
import time
import random
import string
import threading
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from http.client import IncompleteRead
from sqlalchemy.exc import DataError
from sqlalchemy import func as _sa_func

from sqlmodel import Session, select
from app.database import engine
from app.models import MCQ, AnswerOption, Category
from app.models.website import Website
from app.models.websites import Websites
from app.models.top_bar import TopBar
from app.routes.sessionDep import SessionDep
from app.models.scraping_state import ScrapingState, ScrapingStatus
from app.utils.extractors import (
    extract_mcqs_testpoint,
    crawl_pages_testpoint,
    extract_mcqs_pakmcqs,
    crawl_pages_pakmcqs,
    _scrape_mcq_explanation,
    extract_mcqs_pacegkacademy,
    crawl_pages_pacegkacademy
)

# configure a module-level logger
logger = logging.getLogger("scrape")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/scrape")


class ScrapeRequest(BaseModel):
    url:  str   # e.g. "https://testpoint.pk/paper-mcqs/5622/ppsc-all-mcqs-2025"
    slug: str   # must match Category.slug in DB
    scrape_explanations: bool = False  # If True, scrape detailed explanations from individual MCQ pages

    # Optional reliability controls
    chunk_size: int = 25  # pages per background run
    max_pages: Optional[int] = None  # stop after N pages (useful for testing)
    resume: bool = True  # resume existing paused/failed session if available
    state_id: Optional[int] = None  # resume a specific session
    state_name: Optional[str] = None  # human-readable name for this scraping state; auto-generated if not provided
    auto_continue: bool = True  # if True, keep running chunk-after-chunk until done/max_pages/failure
    sleep_between_chunks_seconds: float = 0.0

    # PakMCQs-specific: top-bar link collection
    is_top_bar: bool = False  # If True, also collect top-bar links and store in top_bar / website tables
    top_bar_website_id: Optional[int] = None  # existing websites.id to link top-bar entries to


class ScrapeResponse(BaseModel):
    message: str
    state_id: Optional[int] = None


def _requests_get_html_with_retries(
    url: str,
    *,
    headers: Dict[str, str],
    timeout: tuple = (10, 45),
    max_retries: int = 5,
) -> str:
    """Fetch HTML with retries for transient network/proxy truncations.

    Fixes the common `IncompleteRead` / `Connection broken` issue by:
    - enforcing timeouts
    - disabling compression (`Accept-Encoding: identity`) to avoid truncated gzip bodies
    - retrying with exponential backoff
    """
    last_exc: Optional[BaseException] = None

    # Ensure stable headers
    stable_headers = {
        **headers,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=stable_headers, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except (IncompleteRead, requests.exceptions.ChunkedEncodingError) as e:
            last_exc = e
        except requests.exceptions.RequestException as e:
            # Includes ReadTimeout, ConnectionError, etc.
            last_exc = e

        if attempt < max_retries:
            backoff_s = min(20.0, 1.5 * (2 ** (attempt - 1)))
            logger.warning(f"[scrape] transient fetch error (attempt {attempt}/{max_retries}) for {url}: {last_exc}; sleeping {backoff_s:.1f}s")
            time.sleep(backoff_s)

    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADJECTIVES = [
    "swift", "brave", "calm", "dark", "eager", "fair", "gold", "hardy",
    "idle", "jolly", "keen", "lush", "mild", "neat", "odd", "pure",
    "quick", "rare", "sage", "tall", "umber", "vast", "warm", "xenial",
    "young", "zany",
]
_NOUNS = [
    "atlas", "bloom", "cedar", "dune", "ember", "frost", "grove", "haven",
    "isle", "jade", "kite", "lark", "mesa", "nova", "opal", "pike",
    "quest", "reef", "stone", "tide", "umber", "vale", "wave", "xenon",
    "yarn", "zest",
]


def _random_state_name() -> str:
    """Generate a random human-readable scraping state name like 'swift-nova-4f2a'."""
    adj  = random.choice(_ADJECTIVES)
    noun = random.choice(_NOUNS)
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{adj}-{noun}-{suffix}"


def _slug_for_sub_url(sub_url: str, parent_slug: str) -> str:
    """Derive a slug for a sub-category URL by appending the sub-URL's last
    path segment to the *full* parent slug.

    Example::

        sub_url     = 'https://pakmcqs.com/category/mathematics-mcqs/basic-maths-mcqs'
        parent_slug = 'subjectwise/mathematics-mcqs'
        → 'subjectwise/mathematics-mcqs/basic-maths-mcqs'

    This preserves the full subject → topic hierarchy in the slug.
    """
    from urllib.parse import urlparse as _urlparse
    path_parts = [p for p in _urlparse(sub_url).path.rstrip("/").split("/") if p]
    last_segment = path_parts[-1] if path_parts else "unknown"
    return f"{parent_slug}/{last_segment}"


def _get_or_create_manual_scraping_state(
    *,
    session: Session,
    base_url: str,
    category_id: int,
    category_slug: str,
    max_pages: Optional[int],
    resume: bool,
    state_id: Optional[int],
    state_name: Optional[str] = None,
    mode: str = "chunked-testpoint",
) -> ScrapingState:
    """Create or reuse a ScrapingState for the simplified `/scrape/*` endpoints.

    * If `state_id` is given, that exact state is returned (or 404).
    * If `resume=True`, the most-recent resumable state for (base_url, category_slug) is reused.
    * Otherwise a brand-new state is created.
      - `state_name` is stored as `category_name`; a random adjective-noun name is
        generated automatically when the caller omits it.
    """

    if state_id is not None:
        st = session.exec(select(ScrapingState).where(ScrapingState.id == state_id)).one_or_none()
        if not st:
            raise HTTPException(status_code=404, detail=f"scraping state {state_id} not found")
        return st

    if resume:
        st = session.exec(
            select(ScrapingState).where(
                (ScrapingState.base_url == base_url)
                & (ScrapingState.category_slug == category_slug)
                & (ScrapingState.status.in_([
                    ScrapingStatus.PENDING,
                    ScrapingStatus.IN_PROGRESS,
                    ScrapingStatus.PAUSED,
                    ScrapingStatus.FAILED,
                ]))
            )
        ).first()
        if st:
            logger.info(f"[scrape] resuming existing state id={st.id} name={st.category_name!r}")
            return st

    # Determine a human-readable name for this state
    resolved_name = state_name or _random_state_name()
    logger.info(f"[scrape] creating new ScrapingState name={resolved_name!r} for {base_url!r}")

    st = ScrapingState(
        base_url=base_url,
        website_id=0,
        status=ScrapingStatus.PENDING,
        category_slug=category_slug,
        category_name=resolved_name,     # use the provided / auto-generated name
        max_pages_limit=max_pages,
        validation_source="manual",
        extra_data={
            "mode": mode,
            "category_id": category_id,
            "next_url": base_url,
            "state_name": resolved_name,
        },
    )
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _scrape_and_insert_task(url: str, category_id: int):
    """
    Background task: crawl every page under `url`, parse MCQs,
    and insert them into the database under the given category_id.
    """
    try:
        pages = crawl_pages_testpoint(url)
    except Exception as e:
        logger.error(f"[scrape] crawl failed: {e}")
        return

    inserted = 0
    with Session(engine) as session:
        for page_url in pages:
            logger.info(f"[scrape] fetching {page_url}")
            try:
                html = _requests_get_html_with_retries(
                    page_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=(10, 45),
                    max_retries=5,
                )
            except Exception as e:
                logger.warning(f"[scrape] failed to fetch {page_url}: {e}")
                continue

            soup = BeautifulSoup(html, "html.parser")
            mcqs = extract_mcqs_testpoint(soup)
            logger.info(f"[scrape] extracted {len(mcqs)} MCQs on this page")

            for mcq_data in mcqs:
                mcq = MCQ(**mcq_data, category_id=category_id)
                session.add(mcq)
                inserted += 1

        session.commit()
    logger.info(f"[scrape] done — inserted total {inserted} MCQs into category {category_id}")


def _scrape_and_insert_testpoint_chunk_task(
    state_id: int,
    category_id: int,
    chunk_size: int = 25,
    max_pages: Optional[int] = None,
    auto_continue: bool = True,
    sleep_between_chunks_seconds: float = 0.0,
):
    """Chunked TestPoint scraper that can resume after failures without redoing work.

    If `auto_continue=True`, it will keep processing chunk-after-chunk until completion (or max_pages/failure),
    while still checkpointing state after every page.
    """

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    with Session(engine) as session:
        state = session.exec(select(ScrapingState).where(ScrapingState.id == state_id)).one_or_none()
        if not state:
            logger.error(f"[testpoint] state not found: {state_id}")
            return

        # Ensure state has a next_url
        next_url = (state.extra_data or {}).get("next_url") or state.base_url
        state.extra_data = {**(state.extra_data or {}), "next_url": next_url, "category_id": category_id}

        if state.status in [ScrapingStatus.PENDING, ScrapingStatus.PAUSED, ScrapingStatus.FAILED]:
            state.mark_as_started()
            session.commit()

        while True:
            processed_this_chunk = 0

            while processed_this_chunk < max(1, chunk_size):
                if max_pages is not None and state.pages_processed >= max_pages:
                    logger.info(f"[testpoint] reached max_pages={max_pages}; pausing state_id={state_id}")
                    state.mark_as_paused()
                    session.commit()
                    return

                page_url = (state.extra_data or {}).get("next_url")
                if not page_url:
                    # Safety fallback
                    page_url = state.base_url
                    state.extra_data = {**(state.extra_data or {}), "next_url": page_url}

                logger.info(f"[testpoint] [state {state_id}] processing page {state.pages_processed + 1}: {page_url}")

                try:
                    html = _requests_get_html_with_retries(page_url, headers=headers, timeout=(10, 60), max_retries=6)
                except Exception as e:
                    logger.error(f"[testpoint] [state {state_id}] fetch failed: {page_url}: {e}")
                    state.mark_page_as_failed(page_url, str(e))
                    # Pause so it can be resumed later without losing the next_url
                    state.mark_as_paused()
                    session.commit()
                    return

                soup = BeautifulSoup(html, "html.parser")
                mcqs = extract_mcqs_testpoint(soup)

                page_inserted = 0
                for mcq_data in mcqs:
                    # Avoid autoflush while we do duplicate checks; we only want to flush/commit
                    # after we've processed the page and updated state.
                    with session.no_autoflush:
                        existing = session.exec(
                            select(MCQ).where(
                                (MCQ.question_text == mcq_data["question_text"]) & (MCQ.category_id == category_id)
                            )
                        ).first()
                    if existing:
                        continue
                    session.add(MCQ(**mcq_data, category_id=category_id))
                    page_inserted += 1

                # Find next page
                nxt = soup.select_one('ul.pagination a.page-link[rel=next]')
                if nxt and nxt.get("href"):
                    next_url = urljoin(page_url, nxt["href"])
                else:
                    next_url = None

                # Persist page results + next_url after each page so resume never misses work
                state.pages_processed += 1
                state.current_page_index += 1
                # In sequential pagination we often don't know total upfront; keep this monotonic so progress UI is sane.
                if state.total_pages_discovered < state.pages_processed:
                    state.total_pages_discovered = state.pages_processed
                state.total_mcqs_found += len(mcqs)
                state.total_mcqs_saved += page_inserted
                state.new_mcqs_created += page_inserted
                state.extra_data = {
                    **(state.extra_data or {}),
                    "last_success_url": page_url,
                    "next_url": next_url,
                }
                try:
                    session.commit()
                except DataError as e:
                    # Typically means column sizes are too small in the existing DB schema.
                    session.rollback()
                    state2 = session.exec(select(ScrapingState).where(ScrapingState.id == state_id)).one_or_none()
                    if state2:
                        state2.mark_page_as_failed(page_url, f"db_data_too_long: {e}")
                        state2.mark_as_paused()
                        session.commit()
                    logger.error(
                        f"[testpoint] [state {state_id}] DB DataError (likely column too small). Paused for migration. Page={page_url}: {e}"
                    )
                    return

                logger.info(
                    f"[testpoint] [state {state_id}] page done: inserted {page_inserted}/{len(mcqs)}; total pages={state.pages_processed} total new mcqs={state.new_mcqs_created}"
                )

                processed_this_chunk += 1

                if not next_url:
                    state.mark_as_completed()
                    session.commit()
                    logger.info(f"[testpoint] [state {state_id}] completed")
                    return

            # Chunk boundary reached and we still have next_url
            if auto_continue:
                if sleep_between_chunks_seconds > 0:
                    time.sleep(float(sleep_between_chunks_seconds))
                # keep state IN_PROGRESS and continue next chunk
                continue

            # manual chunk mode: pause so caller can trigger next chunk
            state.mark_as_paused()
            session.commit()
            logger.info(f"[testpoint] [state {state_id}] chunk complete; paused for resume")
            return


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

    # 2) Create/resume a persistent scraping state
    st = _get_or_create_manual_scraping_state(
        session=session,
        base_url=req.url,
        category_id=cat.id,
        category_slug=req.slug,
        max_pages=req.max_pages,
        resume=req.resume,
        state_id=req.state_id,
        state_name=req.state_name,
        mode="chunked-testpoint",
    )

    # 3) Schedule chunked background work (safe to resume)
    logger.info(f"[testpoint] enqueueing chunk task state_id={st.id} name={st.category_name!r}, category_id={cat.id}, url={req.url}, chunk_size={req.chunk_size}")
    threading.Thread(target=_scrape_and_insert_testpoint_chunk_task, args=(
        st.id,
        cat.id,
        req.chunk_size,
        req.max_pages,
        req.auto_continue,
        req.sleep_between_chunks_seconds,
    ), daemon=True).start()

    mode = "auto" if req.auto_continue else "manual"
    return ScrapeResponse(message=f"TestPoint scraping for '{req.slug}' started (chunked/resumable, {mode}, state={st.category_name!r})", state_id=st.id)


@router.post(
    "/testpoint/resume/{state_id}",
    response_model=ScrapeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_scrape_testpoint(
    state_id: int,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    chunk_size: int = 25,
    auto_continue: bool = True,
    sleep_between_chunks_seconds: float = 0.0,
):
    st = session.exec(select(ScrapingState).where(ScrapingState.id == state_id)).one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail=f"scraping state {state_id} not found")
    if st.status not in [ScrapingStatus.PAUSED, ScrapingStatus.FAILED, ScrapingStatus.IN_PROGRESS, ScrapingStatus.PENDING]:
        raise HTTPException(status_code=400, detail=f"state {state_id} not resumable (status={st.status.value})")

    category_id = int((st.extra_data or {}).get("category_id") or 0)
    if category_id <= 0:
        raise HTTPException(status_code=400, detail=f"state {state_id} missing category_id")

    threading.Thread(target=_scrape_and_insert_testpoint_chunk_task, args=(
        st.id,
        category_id,
        chunk_size,
        st.max_pages_limit,
        auto_continue,
        sleep_between_chunks_seconds,
    ), daemon=True).start()
    return ScrapeResponse(message="Resume started", state_id=st.id)


@router.get(
    "/state/{state_id}",
    status_code=status.HTTP_200_OK,
)
def get_scrape_state(state_id: int, session: SessionDep) -> Dict[str, Any]:
    st = session.exec(select(ScrapingState).where(ScrapingState.id == state_id)).one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail=f"scraping state {state_id} not found")
    return st.to_summary_dict() | {"resume_info": st.get_resume_info(), "extra_data": st.extra_data}


def _collect_and_store_table_links(
    session: Session,
    soup: BeautifulSoup,
    page_url: str,
    website_id: int,
) -> List[str]:
    """Parse every `.table-container table a[href]` on the page, persist each link
    to the `top_bar` table (deduped by URL + website_id), and return the list of
    unique absolute URLs found — these become the sub-category scraping queue.

    Each `<th>` heading in the table is used as the section ``title``.
    Each `<a>` text becomes the ``name``.
    """
    discovered_urls: List[str] = []

    # PakMCQs uses two layouts:
    # 1. Old: <div class="table-container"><table>...</table></div>
    # 2. New: <table class="table">...</table>  (no wrapper div)
    containers = soup.select(".table-container table")
    if not containers:
        containers = soup.select("table.table")
    if not containers:
        logger.warning(
            f"[pakmcqs:table_links] no subcategory table found on {page_url}"
        )
        return discovered_urls

    for table in containers:
        # The <th> in that table becomes the section title for all links in the table
        th = table.find("th")
        section_title = th.get_text(strip=True) if th else None
        # Strip the section-title <a> href (it's the category root, already being scraped)
        section_url = None
        if th:
            th_a = th.find("a", href=True)
            if th_a:
                section_url = urljoin(page_url, th_a["href"].strip())

        for a_tag in table.find_all("a", href=True):
            abs_url = urljoin(page_url, a_tag["href"].strip())
            link_name = a_tag.get_text(separator=" ", strip=True)

            # Skip the section-title link itself
            if abs_url == section_url or not link_name:
                continue

            # Persist to top_bar table (skip duplicates)
            existing = session.exec(
                select(TopBar).where(
                    (TopBar.url == abs_url) & (TopBar.website_id == website_id)
                )
            ).first()
            if not existing:
                session.add(TopBar(
                    title=section_title,
                    name=link_name,
                    url=abs_url,
                    website_id=website_id,
                ))

            if abs_url not in discovered_urls:
                discovered_urls.append(abs_url)

    if discovered_urls:
        session.commit()
        logger.info(
            f"[pakmcqs:table_links] stored {len(discovered_urls)} sub-category links "
            f"(website_id={website_id}) from {page_url}"
        )
    return discovered_urls


def _ensure_website_record(
    session: Session,
    base_url: str,
    website_name: str = "PakMCQs",
    website_type: str = "pakmcqs",
) -> int:
    """Return an existing `websites.id` matching *base_url*, or create one.
    Also ensures a matching row exists in the `website` table (is_top_bar=True).
    Returns the `websites.id`.
    """
    parsed = urlparse(base_url)
    canonical = f"{parsed.scheme}://{parsed.netloc}"

    ws = session.exec(
        select(Websites).where(Websites.base_url == canonical)
    ).first()
    if not ws:
        ws = Websites(
            website_name=website_name,
            base_url=canonical,
            website_type=website_type,
            description=f"Auto-created during PakMCQs scrape of {base_url}",
            is_active=True,
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        logger.info(f"[pakmcqs:top_bar] created Websites record id={ws.id} for {canonical!r}")

        # Also create a Website (singular) tracking record with is_top_bar=True
        web = Website(
            is_top_bar=True,
            is_paper_exit=False,
            is_side_bar=False,
            current_page_url=base_url,
            is_last_completed=False,
        )
        session.add(web)
        session.commit()
        logger.info(f"[pakmcqs:top_bar] created Website tracking record web_id={web.web_id}")
    else:
        logger.info(f"[pakmcqs:top_bar] reusing Websites record id={ws.id} for {canonical!r}")

    return ws.id


def _scrape_and_insert_pakmcqs_chunk_task(
    state_id: int,
    category_id: int,
    chunk_size: int = 25,
    max_pages: Optional[int] = None,
    scrape_explanations: bool = False,
    auto_continue: bool = True,
    sleep_between_chunks_seconds: float = 0.0,
    is_top_bar: bool = False,
    top_bar_website_id: Optional[int] = None,
    slug_prefix: Optional[str] = None,   # e.g. "subjectwise" — used to derive per-sub-URL slugs
):
    """Chunked, resumable PakMCQs scraper that checkpoints state after every page.

    Stores the next page URL in `state.extra_data["next_url"]` so the job can be
    resumed after any failure or server restart without re-scraping already-done work.

    If `auto_continue=True` it will keep looping chunk-after-chunk until completion
    (or max_pages / no more pages), just like the TestPoint scraper.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    with Session(engine) as session:
        state = session.exec(select(ScrapingState).where(ScrapingState.id == state_id)).one_or_none()
        if not state:
            logger.error(f"[pakmcqs] state not found: {state_id}")
            return

        # Bootstrap next_url from extra_data or fall back to base_url
        next_url = (state.extra_data or {}).get("next_url") or state.base_url

        # Restore slug_prefix from extra_data (set by enqueue endpoint) if not passed
        if not slug_prefix:
            slug_prefix = (state.extra_data or {}).get("slug_prefix") or None

        # ── Resolve / create Websites + Website records if top_bar is enabled ──
        resolved_top_bar_website_id = top_bar_website_id
        if is_top_bar and not resolved_top_bar_website_id:
            resolved_top_bar_website_id = _ensure_website_record(
                session, base_url=state.base_url
            )

        # The category_id used for MCQ inserts.  For the main URL this is the
        # category_id passed in; for sub-categories it will be overridden inside
        # the loop when we pop from the queue.
        active_category_id: int = category_id

        state.extra_data = {
            **(state.extra_data or {}),
            "next_url": next_url,
            "category_id": category_id,
            "scrape_explanations": scrape_explanations,
            "is_top_bar": is_top_bar,
            "top_bar_website_id": resolved_top_bar_website_id,
            "slug_prefix": slug_prefix,
        }

        if state.status in [ScrapingStatus.PENDING, ScrapingStatus.PAUSED, ScrapingStatus.FAILED]:
            state.mark_as_started()
            session.commit()

        while True:
            processed_this_chunk = 0

            while processed_this_chunk < max(1, chunk_size):
                # ── max_pages guard ──────────────────────────────────────────
                if max_pages is not None and state.pages_processed >= max_pages:
                    logger.info(f"[pakmcqs] reached max_pages={max_pages}; pausing state_id={state_id}")
                    state.mark_as_paused()
                    session.commit()
                    return

                page_url = (state.extra_data or {}).get("next_url")
                if not page_url:
                    page_url = state.base_url
                    state.extra_data = {**(state.extra_data or {}), "next_url": page_url}

                logger.info(
                    f"[pakmcqs] [state {state_id}] processing page "
                    f"{state.pages_processed + 1}: {page_url}"
                )

                # ── fetch page ───────────────────────────────────────────────
                try:
                    html = _requests_get_html_with_retries(
                        page_url, headers=headers, timeout=(10, 60), max_retries=6
                    )
                except Exception as e:
                    logger.error(f"[pakmcqs] [state {state_id}] fetch failed: {page_url}: {e}")
                    state.mark_page_as_failed(page_url, str(e))
                    state.mark_as_paused()
                    session.commit()
                    return

                soup = BeautifulSoup(html, "html.parser")

                # ── On the very first page: discover sub-category URLs from the
                #    .table-container table and queue them for later processing.
                #    BACKBONE: before queueing, check ScrapingState in the DB so
                #    already-completed sub-categories are skipped and the job can
                #    resume exactly where it left off after any interruption. ──
                if (
                    is_top_bar
                    and resolved_top_bar_website_id
                    and "sub_url_queue" not in (state.extra_data or {})
                ):
                    raw_sub_urls = _collect_and_store_table_links(
                        session, soup, page_url, resolved_top_bar_website_id
                    )

                    # ── DATA-DRIVEN deduplication ────────────────────────────
                    # For each discovered sub-URL, derive its Category slug and
                    # check whether that Category already has MCQs in the DB.
                    # This is the canonical truth: if MCQs exist, the sub-category
                    # was already scraped — skip it, regardless of which state did it.
                    # This works correctly after full completion + new state creation,
                    # mid-run restarts, and manual re-requests.
                    already_done: List[str] = []
                    to_queue: List[str] = []

                    for sub_url in raw_sub_urls:
                        sub_slug = (
                            _slug_for_sub_url(sub_url, slug_prefix)
                            if slug_prefix else None
                        )

                        # Primary check: does the Category have MCQs already?
                        skip = False
                        if sub_slug:
                            sub_cat_row = session.exec(
                                select(Category).where(Category.slug == sub_slug)
                            ).one_or_none()
                            if sub_cat_row:
                                mcq_count = session.exec(
                                    select(_sa_func.count(MCQ.id))
                                    .where(MCQ.category_id == sub_cat_row.id)
                                ).one()
                                if mcq_count and mcq_count > 0:
                                    skip = True
                                    already_done.append(sub_url)
                                    logger.info(
                                        f"[pakmcqs] [state {state_id}] sub-category "
                                        f"slug={sub_slug!r} already has {mcq_count} MCQs "
                                        f"— skipping: {sub_url}"
                                    )

                        if not skip:
                            to_queue.append(sub_url)

                    logger.info(
                        f"[pakmcqs] [state {state_id}] discovered {len(raw_sub_urls)} "
                        f"sub-category URLs: {len(to_queue)} queued, "
                        f"{len(already_done)} already have data (skipped)."
                    )

                    state.extra_data = {
                        **(state.extra_data or {}),
                        "sub_url_queue": to_queue,
                        "completed_sub_urls": already_done,
                        "current_sub_category": None,
                    }
                    session.commit()

                    # If every subcategory already had data, there's nothing left to do — 
                    # mark as completed to avoid re-scanning all the root category pages.
                    if raw_sub_urls and not to_queue:
                        logger.info(
                            f"[pakmcqs] [state {state_id}] all {len(raw_sub_urls)} sub-categories "
                            f"already have data. Marking as completed (nothing new to scrape)."
                        )
                        state.mark_as_completed()
                        session.commit()
                        return

                mcqs = extract_mcqs_pakmcqs(soup, scrape_explanations=scrape_explanations)

                # ── insert MCQs (skip duplicates) ────────────────────────────
                page_inserted = 0
                for mcq_data in mcqs:
                    with session.no_autoflush:
                        existing = session.exec(
                            select(MCQ).where(
                                (MCQ.question_text == mcq_data["question_text"])
                                & (MCQ.category_id == active_category_id)
                            )
                        ).first()
                    if existing:
                        continue
                    session.add(MCQ(**mcq_data, category_id=active_category_id))
                    page_inserted += 1

                # ── detect next page using PakMCQs pagination ────────────────
                # PakMCQs uses WordPress-style: /page/2/, /page/3/, … or rel=next
                nxt_tag = soup.select_one('a.next.page-numbers, a[rel=next]')
                if nxt_tag and nxt_tag.get("href"):
                    next_url = urljoin(page_url, nxt_tag["href"])
                else:
                    next_url = None

                # ── checkpoint ──────────────────────────────────────────────
                state.pages_processed += 1
                state.current_page_index += 1
                if state.total_pages_discovered < state.pages_processed:
                    state.total_pages_discovered = state.pages_processed
                state.total_mcqs_found += len(mcqs)
                state.total_mcqs_saved += page_inserted
                state.new_mcqs_created += page_inserted
                state.extra_data = {
                    **(state.extra_data or {}),
                    "last_success_url": page_url,
                    "next_url": next_url,
                }
                try:
                    session.commit()
                except DataError as e:
                    session.rollback()
                    state2 = session.exec(
                        select(ScrapingState).where(ScrapingState.id == state_id)
                    ).one_or_none()
                    if state2:
                        state2.mark_page_as_failed(page_url, f"db_data_too_long: {e}")
                        state2.mark_as_paused()
                        session.commit()
                    logger.error(
                        f"[pakmcqs] [state {state_id}] DB DataError. Paused for migration. Page={page_url}: {e}"
                    )
                    return

                logger.info(
                    f"[pakmcqs] [state {state_id}] page done: "
                    f"inserted {page_inserted}/{len(mcqs)}; "
                    f"total pages={state.pages_processed} total new mcqs={state.new_mcqs_created}"
                )

                processed_this_chunk += 1

                if not next_url:
                    # ── Sub-category queue logic ─────────────────────────────
                    # When is_top_bar=True, instead of completing immediately,
                    # pop the next URL from the queue and continue scraping it.
                    if is_top_bar:
                        queue: List[str] = list(
                            (state.extra_data or {}).get("sub_url_queue", [])
                        )
                        completed: List[str] = list(
                            (state.extra_data or {}).get("completed_sub_urls", [])
                        )
                        current_sub = (state.extra_data or {}).get("current_sub_category")

                        # Mark the current sub-category (or main URL) as done
                        if current_sub and current_sub not in completed:
                            completed.append(current_sub)
                        elif not current_sub:
                            # We just finished the main index page
                            completed.append(page_url)

                        if queue:
                            # Pop next sub-category and start scraping it.
                            # Derive its slug from the slug_prefix and URL path.
                            next_sub = queue.pop(0)

                            # ── Per-sub-URL Category row ────────────────────
                            sub_slug = (
                                _slug_for_sub_url(next_sub, slug_prefix)
                                if slug_prefix
                                else next_sub  # fallback: full URL as slug
                            )
                            sub_cat = session.exec(
                                select(Category).where(Category.slug == sub_slug)
                            ).one_or_none()
                            if not sub_cat:
                                sub_cat_name = sub_slug.split("/")[-1].replace("-", " ").title()
                                sub_cat = Category(slug=sub_slug, name=sub_cat_name)
                                session.add(sub_cat)
                                session.commit()
                                session.refresh(sub_cat)
                                logger.info(
                                    f"[pakmcqs] [state {state_id}] created Category "
                                    f"slug={sub_slug!r} id={sub_cat.id}"
                                )
                            else:
                                logger.info(
                                    f"[pakmcqs] [state {state_id}] reusing Category "
                                    f"slug={sub_slug!r} id={sub_cat.id}"
                                )

                            # Switch active_category_id for subsequent MCQ inserts
                            active_category_id = sub_cat.id

                            state.extra_data = {
                                **(state.extra_data or {}),
                                "sub_url_queue": queue,
                                "completed_sub_urls": completed,
                                "current_sub_category": next_sub,
                                "current_sub_category_id": sub_cat.id,
                                "next_url": next_sub,
                            }
                            session.commit()
                            logger.info(
                                f"[pakmcqs] [state {state_id}] starting sub-category "
                                f"{len(completed)}/{len(completed)+len(queue)}: "
                                f"{next_sub} (slug={sub_slug!r}, cat_id={sub_cat.id})"
                            )
                            processed_this_chunk += 1
                            continue  # back to inner while → fetch next_sub
                        else:
                            # All sub-categories done
                            state.extra_data = {
                                **(state.extra_data or {}),
                                "completed_sub_urls": completed,
                                "current_sub_category": None,
                                "next_url": None,
                            }
                            state.mark_as_completed()
                            session.commit()
                            logger.info(
                                f"[pakmcqs] [state {state_id}] all sub-categories done "
                                f"({len(completed)} processed). Completed."
                            )
                            return
                    else:
                        state.mark_as_completed()
                        session.commit()
                        logger.info(f"[pakmcqs] [state {state_id}] completed — no more pages.")
                        return

            # ── chunk boundary ───────────────────────────────────────────────
            if auto_continue:
                if sleep_between_chunks_seconds > 0:
                    time.sleep(float(sleep_between_chunks_seconds))
                continue  # keep running without pausing

            # Manual chunk mode: pause so caller can trigger the next chunk
            state.mark_as_paused()
            session.commit()
            logger.info(f"[pakmcqs] [state {state_id}] chunk complete; paused for resume")
            return


@router.post(
    "/pakmcqs",
    response_model=ScrapeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_scrape_pakmcqs(
    req: ScrapeRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
):
    """Scrape PakMCQs.com — chunked & resumable via ScrapingState.

    * main the catagories as 
      - subjectwise/catagory_name(subjact name)/topics_name(topics name)/sub_topics_name(sub topics name)/mcqs
    
    * sub_topics_name is optional
    
    * mcqs is the main page
    """
    # ── Validate slug format when is_top_bar=True ──────────────────────────
    # The slug MUST be in "prefix/topic" form (e.g. "subjectwise/mathematics-mcqs")
    # so we know which prefix to use for derived sub-category slugs.
    if req.is_top_bar and "/" not in req.slug:
        raise HTTPException(
            status_code=422,
            detail=(
                "When is_top_bar=True the slug must include a prefix separated by '/', "
                f"e.g. 'subjectwise/{req.slug}'.  Got: {req.slug!r}"
            ),
        )

    # slug_prefix here stores the FULL parent slug (e.g. "subjectwise/mathematics-mcqs")
    # so that derived sub-category slugs become "subjectwise/mathematics-mcqs/basic-maths-mcqs".
    slug_prefix = req.slug if req.is_top_bar else None

    # 1) Resolve / auto-create Category
    cat = session.exec(select(Category).where(Category.slug == req.slug)).one_or_none()
    if not cat:
        logger.info(f"[pakmcqs] creating Category slug={req.slug!r}")
        cat = Category(slug=req.slug, name=req.slug.replace("_", " ").replace("/", " / ").title())
        session.add(cat)
        session.commit()
        session.refresh(cat)

    # 2) Auto-resume: if the same base URL is requested again and no explicit
    #    state_id is provided, find the latest resumable state for this URL
    #    and re-use it rather than spawning a duplicate run.
    explicit_state_id = req.state_id if req.state_id else None
    if not explicit_state_id and req.resume:
        existing = session.exec(
            select(ScrapingState)
            .where(
                (ScrapingState.base_url == req.url)
                & (ScrapingState.status.in_([
                    ScrapingStatus.PAUSED,
                    ScrapingStatus.FAILED,
                    ScrapingStatus.IN_PROGRESS,
                    ScrapingStatus.PENDING,
                ]))
            )
            .order_by(ScrapingState.id.desc())
        ).first()
        if existing:
            explicit_state_id = existing.id
            logger.info(
                f"[pakmcqs] auto-resume: found existing state id={existing.id} "
                f"name={existing.category_name!r} for base_url={req.url!r}"
            )

    # 3) Create / resume a persistent ScrapingState
    st = _get_or_create_manual_scraping_state(
        session=session,
        base_url=req.url,
        category_id=cat.id,
        category_slug=req.slug,
        max_pages=req.max_pages,
        resume=req.resume,
        state_id=explicit_state_id,
        state_name=req.state_name,
        mode="chunked-pakmcqs",
    )

    # Persist slug_prefix in extra_data so resume picks it up automatically
    if slug_prefix:
        st.extra_data = {**(st.extra_data or {}), "slug_prefix": slug_prefix}
        session.commit()

    logger.info(
        f"[pakmcqs] enqueueing chunk task state_id={st.id} name={st.category_name!r}, "
        f"category_id={cat.id}, url={req.url}, chunk_size={req.chunk_size}, "
        f"is_top_bar={req.is_top_bar}, slug_prefix={slug_prefix!r}"
    )
    threading.Thread(target=_scrape_and_insert_pakmcqs_chunk_task, args=(
        st.id,
        cat.id,
        req.chunk_size,
        req.max_pages,
        req.scrape_explanations,
        req.auto_continue,
        req.sleep_between_chunks_seconds,
        req.is_top_bar,
        req.top_bar_website_id,
        slug_prefix,
    ), daemon=True).start()

    mode = "auto" if req.auto_continue else "manual"
    explanation_msg = " with explanations" if req.scrape_explanations else ""
    top_bar_msg = ", top-bar links collected" if req.is_top_bar else ""
    return ScrapeResponse(
        message=f"PakMCQs scraping of '{req.slug}'{explanation_msg}{top_bar_msg} started (chunked/resumable, {mode}, state={st.category_name!r})",
        state_id=st.id,
    )


@router.post(
    "/pakmcqs/resume/{state_id}",
    response_model=ScrapeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_scrape_pakmcqs(
    state_id: int,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    chunk_size: int = 25,
    auto_continue: bool = True,
    sleep_between_chunks_seconds: float = 0.0,
):
    """Resume a paused/failed PakMCQs scraping state."""
    st = session.exec(select(ScrapingState).where(ScrapingState.id == state_id)).one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail=f"scraping state {state_id} not found")
    if st.status not in [
        ScrapingStatus.PAUSED, ScrapingStatus.FAILED,
        ScrapingStatus.IN_PROGRESS, ScrapingStatus.PENDING,
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"state {state_id} not resumable (status={st.status.value})",
        )

    category_id = int((st.extra_data or {}).get("category_id") or 0)
    if category_id <= 0:
        raise HTTPException(status_code=400, detail=f"state {state_id} missing category_id")

    scrape_explanations = bool((st.extra_data or {}).get("scrape_explanations", False))
    # Restore top-bar settings from the persisted state so a resumed session
    # continues with the same configuration as the original run.
    is_top_bar = bool((st.extra_data or {}).get("is_top_bar", False))
    top_bar_website_id_raw = (st.extra_data or {}).get("top_bar_website_id")
    top_bar_website_id = int(top_bar_website_id_raw) if top_bar_website_id_raw else None
    slug_prefix = (st.extra_data or {}).get("slug_prefix") or None

    threading.Thread(target=_scrape_and_insert_pakmcqs_chunk_task, args=(
        st.id,
        category_id,
        chunk_size,
        st.max_pages_limit,
        scrape_explanations,
        auto_continue,
        sleep_between_chunks_seconds,
        is_top_bar,
        top_bar_website_id,
        slug_prefix,
    ), daemon=True).start()
    state_label = st.category_name or f"state-{st.id}"
    return ScrapeResponse(message=f"PakMCQs resume started (state={state_label!r})", state_id=st.id)


def _scrape_and_insert_pacegkacademy_task(url: str, category_id: int, scrape_explanations: bool = False):
    """
    Background task for PaceGKAcademy: crawl and process pages in chunks.
    Processes pages as they are discovered to avoid memory issues.
    
    Args:
        url: Starting URL to scrape
        category_id: Category ID to insert MCQs into
        scrape_explanations: If True, follow detail links and scrape explanations
    """
    chunk_size = 50
    chunk_number = 0
    total_inserted = 0
    total_pages_processed = 0
    
    try:
        logger.info(f"[pacegkacademy] starting chunked crawl for {url}")
        
        # Process pages in chunks - crawl chunk_size pages at a time
        while True:
            chunk_number += 1
            
            # Calculate starting page for this chunk
            if chunk_number == 1:
                chunk_url = url
            else:
                # Build URL for next chunk starting point
                chunk_url = f"{url}/page/{total_pages_processed + 1}"
            
            chunk_start_page = total_pages_processed + 1
            chunk_end_page = total_pages_processed + chunk_size
            
            logger.info(f"[pacegkacademy] ========== CHUNK {chunk_number} START (Pages {chunk_start_page}-{chunk_end_page}) ==========")
            
            # Crawl up to chunk_size pages
            chunk_pages = crawl_pages_pacegkacademy(chunk_url, max_pages=chunk_size)
            
            if not chunk_pages:
                logger.info(f"[pacegkacademy] no more pages found, stopping")
                break
            
            actual_chunk_end = chunk_start_page + len(chunk_pages) - 1
            logger.info(f"[pacegkacademy] [Chunk {chunk_number}] Crawled {len(chunk_pages)} pages (Pages {chunk_start_page}-{actual_chunk_end})")
            
            # Process this chunk
            inserted = _process_pacegkacademy_pages(chunk_pages, category_id, chunk_number, chunk_start_page, scrape_explanations)
            total_inserted += inserted
            total_pages_processed += len(chunk_pages)
            
            logger.info(f"[pacegkacademy] ========== CHUNK {chunk_number} COMPLETE ==========")
            logger.info(f"[pacegkacademy] [Chunk {chunk_number}] Inserted {inserted} new MCQs from pages {chunk_start_page}-{actual_chunk_end}")
            logger.info(f"[pacegkacademy] [Progress] Total: {total_inserted} MCQs from {total_pages_processed} pages processed")
            logger.info(f"[pacegkacademy] ========================================")
            
            # If we got fewer pages than chunk_size, we've reached the end
            if len(chunk_pages) < chunk_size:
                logger.info(f"[pacegkacademy] reached last page (got {len(chunk_pages)} < {chunk_size})")
                break
                
            # Sleep between chunks to prevent socket bombing
            import time
            logger.info(f"[pacegkacademy] Sleeping for 4 seconds before next chunk to prevent socket hanging...")
            time.sleep(4)
        
        logger.info(f"[pacegkacademy] Done — inserted {total_inserted} MCQs into category {category_id} from {total_pages_processed} pages")
        
    except Exception as e:
        logger.error(f"[pacegkacademy] Task failed: {e}", exc_info=True)


def _process_pacegkacademy_pages(pages: List[str], category_id: int, chunk_number: int, start_page_num: int, scrape_explanations: bool = False) -> int:
    """
    Process a list of page URLs and insert MCQs into the database.
    
    Args:
        pages: List of page URLs to process
        category_id: Category ID to insert MCQs into
        chunk_number: Current chunk number for logging
        start_page_num: Starting page number for this chunk
        scrape_explanations: If True, scrape detailed explanations
    
    Returns:
        Number of MCQs inserted
    """
    inserted = 0
    
    with Session(engine) as session:
        for idx, page_url in enumerate(pages, 1):
            page_num = start_page_num + idx - 1
            logger.info(f"[pacegkacademy] [Chunk {chunk_number}] Processing page {page_num}/{start_page_num + len(pages) - 1}: {page_url}")
            
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "gzip, deflate"
                }
                resp = requests.get(page_url, headers=headers, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"[pacegkacademy] [Chunk {chunk_number}] Failed to fetch page {page_num}: {e}")
                continue
            
            soup = BeautifulSoup(resp.text, "html.parser")
            mcqs = extract_mcqs_pacegkacademy(soup, scrape_explanations=scrape_explanations)
            
            page_inserted = 0
            
            for mcq_data in mcqs:
                # Check for duplicates without triggering autoflush of pending inserts
                with session.no_autoflush:
                    existing = session.exec(
                        select(MCQ).where(
                            (MCQ.question_text == mcq_data["question_text"]) &
                            (MCQ.category_id == category_id)
                        )
                    ).first()
                
                if not existing:
                    mcq = MCQ(**mcq_data, category_id=category_id)
                    session.add(mcq)
                    inserted += 1
                    page_inserted += 1
            
            # Commit after EACH page so we don't hold the DB transaction open during HTTP fetches
            session.commit()
            
            logger.info(f"[pacegkacademy] [Chunk {chunk_number}] Page {page_num}: inserted {page_inserted}/{len(mcqs)} MCQs (skipped {len(mcqs) - page_inserted} duplicates)")
    
    return inserted


@router.post(
    "/pacegkacademy",
    response_model=ScrapeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_scrape_pacegkacademy(
    req: ScrapeRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
):
    """Endpoint for scraping PaceGKAcademy.com with its specific structure"""
    # 1) Look up the Category row in the DB (or create it if missing)
    cat = session.exec(select(Category).where(Category.slug == req.slug)).one_or_none()
    if not cat:
        # auto-create the category record
        logger.info(f"[pacegkacademy] creating Category slug={req.slug!r}")
        cat = Category(slug=req.slug, name=req.slug.replace("_", " ").title())
        session.add(cat)
        session.commit()
        session.refresh(cat)

    # 2) Schedule the background task with PaceGKAcademy-specific extractor
    logger.info(f"[pacegkacademy] enqueueing task for category_id={cat.id}, url={req.url}, scrape_explanations={req.scrape_explanations}")
    threading.Thread(target=_scrape_and_insert_pacegkacademy_task, args=(
        req.url, cat.id, req.scrape_explanations
    ), daemon=True).start()

    explanation_msg = " with explanations" if req.scrape_explanations else ""
    return ScrapeResponse(message=f"PaceGKAcademy scraping of '{req.slug}'{explanation_msg} started")


# ===========================================================================
# PakMCQs — Explanation Backfill
# ===========================================================================
#
# Strategy (the "smart work"):
#   1. Query the DB for MCQs in a given category that still have
#      explanation = NULL.
#   2. Walk the PakMCQs listing pages for that category to build a
#      question_text -> detail_url index.
#   3. Call _scrape_mcq_explanation(detail_url) for each MCQ.
#   4. UPDATE the DB row + commit after every single MCQ (checkpoint).
#   5. Track processed IDs in ScrapingState.extra_data for full resumability.
#
#   All fetches are SEQUENTIAL with a configurable delay — no parallel sockets.
# ===========================================================================


class ExplainRequest(BaseModel):
    """Request body for the explanation-backfill endpoint."""
    slug: str                              # category slug to backfill
    base_url: str                          # PakMCQs listing URL for that category
    state_id: Optional[int] = None        # resume an existing state
    state_name: Optional[str] = None      # human name; auto-generated if omitted
    batch_size: int = 50                  # MCQs to process per background run
    sleep_between_requests: float = 1.0   # seconds between detail-page fetches
    auto_continue: bool = True            # keep going until all MCQs are done
    max_mcqs: Optional[int] = None        # cap total MCQs updated (for dry-runs)


def _backfill_explanations_task(
    state_id: int,
    category_id: int,
    base_url: str,
    batch_size: int = 50,
    sleep_between_requests: float = 1.0,
    auto_continue: bool = True,
    max_mcqs: Optional[int] = None,
) -> None:
    """Sequential, resumable explanation-backfill background task.

    For every MCQ in the given category that has ``explanation IS NULL``:
      1. Walk the PakMCQs listing pages to find the article whose
         question_text matches the DB row and grab its detail URL.
      2. Call ``_scrape_mcq_explanation`` to parse the explanation.
      3. UPDATE the MCQ row and checkpoint the ScrapingState.

    Strictly sequential with a configurable sleep so we never spam the server.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    with Session(engine) as session:
        state = session.exec(
            select(ScrapingState).where(ScrapingState.id == state_id)
        ).one_or_none()
        if not state:
            logger.error(f"[explain_backfill] state not found: {state_id}")
            return

        if state.status in [ScrapingStatus.PENDING, ScrapingStatus.PAUSED, ScrapingStatus.FAILED]:
            state.mark_as_started()
            session.commit()

        # IDs already processed (restored from extra_data for resume)
        done_ids: List[int] = list((state.extra_data or {}).get("done_mcq_ids", []))
        updated_total: int = int((state.extra_data or {}).get("updated_total", 0))

        # Get the root category slug to find all subcategories
        root_cat = session.get(Category, category_id)
        if not root_cat:
            logger.error(f"[explain_backfill] category not found: {category_id}")
            return
            
        root_slug = root_cat.slug
        prefix_slug = f"{root_slug}/"
        
        # Find all category IDs in the tree (root + children)
        cat_ids_in_tree = session.exec(
            select(Category.id).where(
                (Category.slug == root_slug) | (Category.slug.startswith(prefix_slug))
            )
        ).all()

        # Calculate total target for progress logging
        total_target = session.exec(
            select(_sa_func.count(MCQ.id))
            .where((MCQ.category_id.in_(cat_ids_in_tree)) & (MCQ.explanation.is_(None)))
        ).one()
        # Add what we've already done to the currently remaining ones to get the grand total
        grand_total = total_target + updated_total

        while True:
            # ─ 1. Fetch next batch of MCQs without explanations ──────────────────
            query = (
                select(MCQ)
                .where(
                    (MCQ.category_id.in_(cat_ids_in_tree)) & 
                    (MCQ.explanation.is_(None))
                )
                .limit(batch_size)
            )
            pending_mcqs = session.exec(query).all()


            if not pending_mcqs:
                logger.info(
                    f"[explain_backfill] [state {state_id}] no more MCQs to explain. "
                    f"Total Processed: {len(done_ids)}/{grand_total} (Updated: {updated_total})"
                )
                state.extra_data = {
                    **(state.extra_data or {}),
                    "done_mcq_ids": done_ids,
                    "updated_total": updated_total,
                }
                state.mark_as_completed()
                session.commit()
                return

            if max_mcqs is not None and updated_total >= max_mcqs:
                logger.info(f"[explain_backfill] [state {state_id}] reached max_mcqs={max_mcqs}; pausing.")
                state.mark_as_paused()
                session.commit()
                return

            logger.info(
                f"[explain_backfill] [state {state_id}] batch of {len(pending_mcqs)} MCQs "
                f"(Processed: {len(done_ids)}/{grand_total}, Updated: {updated_total})"
            )

            # ─ 2. Build question_text -> detail_url by constructing URLs directly ──
            # PakMCQs detail page URLs follow a predictable pattern:
            #   https://pakmcqs.com/{category-path}/{question-slug}
            # where {category-path} replaces "subjectwise/" with just the category
            # piece, and {question-slug} is the question text lowercased, stripped,
            # spaces replaced with hyphens, and special chars removed.
            # This avoids scanning hundreds of listing pages to find the match.
            import html as _html
            import unicodedata

            def _question_to_slug(q: str) -> str:
                """Convert a question text to the PakMCQs URL slug."""
                # Strip Q. numbering prefix like "Q. 1." or "1."
                q = re.sub(r'^Q\.?\s*\d+[\.:)\s]*', '', q).strip()
                # Decode HTML entities
                q = _html.unescape(q)
                # Normalize unicode
                q = unicodedata.normalize("NFKD", q)
                # Lowercase
                q = q.lower()
                # Replace everything that isn't alphanumeric with a dash
                q = re.sub(r'[^a-z0-9]+', '-', q)
                # Strip leading/trailing dashes and collapse consecutive dashes
                q = re.sub(r'-+', '-', q).strip('-')
                return q

            def _cat_slug_to_pakmcqs_path(cat_slug: str) -> str:
                """Convert DB category slug to the PakMCQs category path segment."""
                suffix = cat_slug
                if suffix.startswith("subjectwise/"):
                    suffix = suffix.replace("subjectwise/", "", 1)
                return suffix

            # Build a map of mcq -> category so we can construct per-MCQ detail URLs
            category_cache: Dict[int, Category] = {}
            for mcq in pending_mcqs:
                if mcq.category_id not in category_cache:
                    cat = session.get(Category, mcq.category_id)
                    if cat:
                        category_cache[mcq.category_id] = cat

            detail_url_cache: Dict[str, Optional[str]] = {}
            for mcq in pending_mcqs:
                cat = category_cache.get(mcq.category_id)
                if cat:
                    cat_path = _cat_slug_to_pakmcqs_path(cat.slug)
                    q_slug = _question_to_slug(mcq.question_text)
                    detail_url = f"https://pakmcqs.com/{cat_path}/{q_slug}"
                    detail_url_cache[mcq.question_text] = detail_url
                else:
                    detail_url_cache[mcq.question_text] = None


            # ─ 3. Fetch explanation for each MCQ and update DB ────────────────
            for mcq in pending_mcqs:
                if max_mcqs is not None and updated_total >= max_mcqs:
                    break

                q_norm = re.sub(r'^Q\.?\s*\d+[\.:)\s]*', '', mcq.question_text).strip()
                detail_url = (
                    detail_url_cache.get(q_norm)
                    or detail_url_cache.get(mcq.question_text)
                )

                if not detail_url:
                    logger.debug(
                        f"[explain_backfill] no detail URL for MCQ id={mcq.id}: "
                        f"{mcq.question_text[:60]!r} — marking as skipped"
                    )
                    
                    db_mcq = session.get(MCQ, mcq.id)
                    if db_mcq:
                        db_mcq.explanation = "[NO_EXPLANATION]"
                        session.add(db_mcq)
                    
                    done_ids.append(mcq.id)
                else:
                    logger.info(
                        f"[explain_backfill] fetching explanation MCQ id={mcq.id}: {detail_url}"
                    )
                    explanation = _scrape_mcq_explanation(detail_url)

                    db_mcq = session.get(MCQ, mcq.id)
                    if db_mcq:
                        if explanation:
                            db_mcq.explanation = explanation
                            updated_total += 1
                            logger.info(
                                f"[explain_backfill] updated MCQ id={mcq.id} ({len(explanation)} chars)"
                            )
                        else:
                            logger.debug(
                                f"[explain_backfill] no explanation content at {detail_url} for MCQ id={mcq.id}"
                            )
                            db_mcq.explanation = "[NO_EXPLANATION]"
                            
                        session.add(db_mcq)
                        
                    done_ids.append(mcq.id)

                # Checkpoint after every single MCQ
                state.extra_data = {
                    **(state.extra_data or {}),
                    "done_mcq_ids": done_ids,
                    "updated_total": updated_total,
                }
                state.total_mcqs_saved = updated_total
                session.commit()


            # ─ Batch boundary ────────────────────────────────────────────
            if not auto_continue:
                state.mark_as_paused()
                session.commit()
                logger.info(
                    f"[explain_backfill] [state {state_id}] batch paused for resume. "
                    f"Total updated: {updated_total}"
                )
                return

            logger.info(
                f"[explain_backfill] [state {state_id}] batch done ({updated_total} total). Continuing..."
            )


@router.post(
    "/pakmcqs/backfill-explanations",
    response_model=ScrapeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def backfill_explanations_pakmcqs(
    req: ExplainRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
):
    """Start (or resume) a sequential explanation-backfill job for a PakMCQs category.

    Walks the existing MCQs in the DB that have ``explanation = NULL``,
    fetches their detail pages on PakMCQs.com one-by-one, and saves the parsed
    explanation back to the DB.  Far more server-friendly than inline scraping.
    """
    cat = session.exec(select(Category).where(Category.slug == req.slug)).one_or_none()
    if not cat:
        raise HTTPException(
            status_code=404,
            detail=f"Category '{req.slug}' not found. Scrape its MCQs first.",
        )

    pending = session.exec(
        select(MCQ).where((MCQ.category_id == cat.id) & (MCQ.explanation.is_(None)))
    ).all()
    if not pending:
        return ScrapeResponse(
            message=f"All MCQs in '{req.slug}' already have explanations — nothing to do.",
            state_id=None,
        )

    st = _get_or_create_manual_scraping_state(
        session=session,
        base_url=req.base_url,
        category_id=cat.id,
        category_slug=req.slug,
        max_pages=None,
        resume=req.state_id is None,
        state_id=req.state_id,
        state_name=req.state_name,
        mode="explain-backfill-pakmcqs",
    )

    logger.info(
        f"[explain_backfill] enqueueing state_id={st.id} name={st.category_name!r}, "
        f"category_id={cat.id}, pending={len(pending)} MCQs"
    )

    threading.Thread(target=_backfill_explanations_task, args=(
        st.id,
        cat.id,
        req.base_url,
        req.batch_size,
        req.sleep_between_requests,
        req.auto_continue,
        req.max_mcqs,
    ), daemon=True).start()

    mode = "auto" if req.auto_continue else "manual batches"
    return ScrapeResponse(
        message=(
            f"Explanation backfill for '{req.slug}' started "
            f"({len(pending)} MCQs pending, {mode}, state={st.category_name!r})"
        ),
        state_id=st.id,
    )


@router.post(
    "/pakmcqs/backfill-explanations/resume/{state_id}",
    response_model=ScrapeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_backfill_explanations_pakmcqs(
    state_id: int,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    batch_size: int = 50,
    sleep_between_requests: float = 1.0,
    auto_continue: bool = True,
):
    """Resume a paused/failed explanation-backfill state."""
    st = session.exec(select(ScrapingState).where(ScrapingState.id == state_id)).one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail=f"scraping state {state_id} not found")
    if st.status not in [
        ScrapingStatus.PAUSED, ScrapingStatus.FAILED,
        ScrapingStatus.IN_PROGRESS, ScrapingStatus.PENDING,
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"state {state_id} not resumable (status={st.status.value})",
        )

    category_id = int((st.extra_data or {}).get("category_id") or 0)
    if category_id <= 0:
        raise HTTPException(status_code=400, detail=f"state {state_id} missing category_id")

    threading.Thread(target=_backfill_explanations_task, args=(
        st.id,
        category_id,
        st.base_url,
        batch_size,
        sleep_between_requests,
        auto_continue,
        None,
    ), daemon=True).start()

    state_label = st.category_name or f"state-{st.id}"
    return ScrapeResponse(
        message=f"Explanation backfill resumed (state={state_label!r})",
        state_id=st.id,
    )
