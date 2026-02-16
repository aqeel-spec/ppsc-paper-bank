import logging
import time
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from http.client import IncompleteRead
from sqlalchemy.exc import DataError

from sqlmodel import Session, select
from app.database import engine
from app.models import MCQ, AnswerOption, Category
from app.routes.sessionDep import SessionDep
from app.models.scraping_state import ScrapingState, ScrapingStatus
from app.utils.extractors import (
    extract_mcqs_testpoint,
    crawl_pages_testpoint,
    extract_mcqs_pakmcqs,
    crawl_pages_pakmcqs,
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
    auto_continue: bool = True  # if True, keep running chunk-after-chunk until done/max_pages/failure
    sleep_between_chunks_seconds: float = 0.0


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


def _get_or_create_manual_scraping_state(
    *,
    session: Session,
    base_url: str,
    category_id: int,
    category_slug: str,
    max_pages: Optional[int],
    resume: bool,
    state_id: Optional[int],
) -> ScrapingState:
    """Create or reuse a ScrapingState for the simplified `/scrape/*` endpoints."""

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
                & (ScrapingState.status.in_([ScrapingStatus.PENDING, ScrapingStatus.IN_PROGRESS, ScrapingStatus.PAUSED, ScrapingStatus.FAILED]))
            )
        ).first()
        if st:
            return st

    st = ScrapingState(
        base_url=base_url,
        website_id=0,
        status=ScrapingStatus.PENDING,
        category_slug=category_slug,
        category_name=category_slug,
        max_pages_limit=max_pages,
        validation_source="manual",
        extra_data={
            "mode": "chunked-testpoint",
            "category_id": category_id,
            "next_url": base_url,
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
    )

    # 3) Schedule chunked background work (safe to resume)
    logger.info(f"[testpoint] enqueueing chunk task state_id={st.id}, category_id={cat.id}, url={req.url}, chunk_size={req.chunk_size}")
    background_tasks.add_task(
        _scrape_and_insert_testpoint_chunk_task,
        st.id,
        cat.id,
        req.chunk_size,
        req.max_pages,
        req.auto_continue,
        req.sleep_between_chunks_seconds,
    )

    mode = "auto" if req.auto_continue else "manual"
    return ScrapeResponse(message=f"TestPoint scraping for '{req.slug}' started (chunked/resumable, {mode})", state_id=st.id)


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

    background_tasks.add_task(
        _scrape_and_insert_testpoint_chunk_task,
        st.id,
        category_id,
        chunk_size,
        st.max_pages_limit,
        auto_continue,
        sleep_between_chunks_seconds,
    )
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


def _scrape_and_insert_pakmcqs_task(url: str, category_id: int, scrape_explanations: bool = False):
    """
    Background task for PakMCQs: crawl and process pages in chunks.
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
        logger.info(f"[pakmcqs] starting chunked crawl for {url}")
        
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
            
            logger.info(f"[pakmcqs] ========== CHUNK {chunk_number} START (Pages {chunk_start_page}-{chunk_end_page}) ==========")
            
            # Crawl up to chunk_size pages
            chunk_pages = crawl_pages_pakmcqs(chunk_url, max_pages=chunk_size)
            
            if not chunk_pages:
                logger.info(f"[pakmcqs] no more pages found, stopping")
                break
            
            actual_chunk_end = chunk_start_page + len(chunk_pages) - 1
            logger.info(f"[pakmcqs] [Chunk {chunk_number}] Crawled {len(chunk_pages)} pages (Pages {chunk_start_page}-{actual_chunk_end})")
            
            # Process this chunk
            inserted = _process_pakmcqs_pages(chunk_pages, category_id, chunk_number, chunk_start_page, scrape_explanations)
            total_inserted += inserted
            total_pages_processed += len(chunk_pages)
            
            logger.info(f"[pakmcqs] ========== CHUNK {chunk_number} COMPLETE ==========")
            logger.info(f"[pakmcqs] [Chunk {chunk_number}] Inserted {inserted} new MCQs from pages {chunk_start_page}-{actual_chunk_end}")
            logger.info(f"[pakmcqs] [Progress] Total: {total_inserted} MCQs from {total_pages_processed} pages processed")
            logger.info(f"[pakmcqs] ========================================")
            
            # If we got fewer pages than chunk_size, we've reached the end
            if len(chunk_pages) < chunk_size:
                logger.info(f"[pakmcqs] reached last page (got {len(chunk_pages)} < {chunk_size})")
                break
        
        logger.info(f"[pakmcqs] Done — inserted {total_inserted} MCQs into category {category_id} from {total_pages_processed} pages")
        
    except Exception as e:
        logger.error(f"[pakmcqs] Task failed: {e}", exc_info=True)


def _process_pakmcqs_pages(pages: List[str], category_id: int, chunk_number: int, start_page_num: int, scrape_explanations: bool = False) -> int:
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
            logger.info(f"[pakmcqs] [Chunk {chunk_number}] Processing page {page_num}/{start_page_num + len(pages) - 1}: {page_url}")
            
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "gzip, deflate"
                }
                resp = requests.get(page_url, headers=headers, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"[pakmcqs] [Chunk {chunk_number}] Failed to fetch page {page_num}: {e}")
                continue
            
            soup = BeautifulSoup(resp.text, "html.parser")
            mcqs = extract_mcqs_pakmcqs(soup, scrape_explanations=scrape_explanations)
            
            page_inserted = 0
            
            for mcq_data in mcqs:
                # Check for duplicates
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
            
            logger.info(f"[pakmcqs] [Chunk {chunk_number}] Page {page_num}: inserted {page_inserted}/{len(mcqs)} MCQs (skipped {len(mcqs) - page_inserted} duplicates)")
        
        session.commit()
    
    return inserted


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
    """Endpoint for scraping PakMCQs.com with its specific structure"""
    # 1) Look up the Category row in the DB (or create it if missing)
    cat = session.exec(select(Category).where(Category.slug == req.slug)).one_or_none()
    if not cat:
        # auto-create the category record
        logger.info(f"[pakmcqs] creating Category slug={req.slug!r}")
        cat = Category(slug=req.slug, name=req.slug.replace("_", " ").title())
        session.add(cat)
        session.commit()
        session.refresh(cat)

    # 2) Schedule the background task with PakMCQs-specific extractor
    logger.info(f"[pakmcqs] enqueueing task for category_id={cat.id}, url={req.url}, scrape_explanations={req.scrape_explanations}")
    background_tasks.add_task(_scrape_and_insert_pakmcqs_task, req.url, cat.id, req.scrape_explanations)

    explanation_msg = " with explanations" if req.scrape_explanations else ""
    return ScrapeResponse(message=f"PakMCQs scraping of '{req.slug}'{explanation_msg} started")


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
                # Check for duplicates
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
            
            logger.info(f"[pacegkacademy] [Chunk {chunk_number}] Page {page_num}: inserted {page_inserted}/{len(mcqs)} MCQs (skipped {len(mcqs) - page_inserted} duplicates)")
        
        session.commit()
    
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
    background_tasks.add_task(_scrape_and_insert_pacegkacademy_task, req.url, cat.id, req.scrape_explanations)

    explanation_msg = " with explanations" if req.scrape_explanations else ""
    return ScrapeResponse(message=f"PaceGKAcademy scraping of '{req.slug}'{explanation_msg} started")
