# app/routes/mcqs.py

import asyncio
import random
from math import ceil
from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select, desc, func

from app.models.mcq import (
    MCQ, MCQCreate, MCQUpdate, MCQBulkCreate,
    Category
)
from .sessionDep import SessionDep  # yields a sync Session

router = APIRouter(prefix="/mcqs")


# ── Helper / Response Models ─────────────────────────────────────────────────

class Pagination(BaseModel):
    total_items:   int
    total_pages:   int
    current_page:  int
    per_page:      int
    has_next_page: bool
    has_prev_page: bool

class MCQPage(BaseModel):
    pagination: Pagination
    data:       List[MCQ]

class BulkMCQCreateResponse(BaseModel):
    mcqs:             List[MCQ]
    total_added:      int
    category_counts:  Dict[str,int]
    total_categories: int

class StatsResponse(BaseModel):
    total_questions:  int
    category_counts:  Dict[str,int]
    total_categories: int

class RepeatedQuestion(BaseModel):
    question_text: str
    count:         int
    

class CategoryResponse(BaseModel):
    slug: str
    name: str


def _maybe_await(result):
    """
    Some of our session.commit()/refresh calls may return coroutines
    under certain async models.  This helper fuses them.
    """
    if asyncio.iscoroutine(result):
        return asyncio.get_event_loop().run_until_complete(result)
    return result


@router.get("/catagories", response_model=List[Category])
def list_categories(session: SessionDep):
    """
    Return all MCQ categories (id, slug, name, timestamps).
    Clients can use this to populate their dropdown.
    """
    cats = session.exec(select(Category)).all()
    return cats
# ── 1) Create a single MCQ ────────────────────────────────────────────────

@router.post("/", response_model=MCQ, status_code=status.HTTP_201_CREATED)
def create_mcq(payload: MCQCreate, session: SessionDep):
    # 1) either find existing…
    if payload.category_slug:
        cat = session.exec(
            select(Category).where(Category.slug == payload.category_slug)
        ).one_or_none()
        if not cat:
            raise HTTPException(404, f"Category slug '{payload.category_slug}' not found")
    else:
        # 2) or create a new Category row
        cat = Category(
            slug=payload.new_category_slug,
            name=payload.new_category_name
        )
        session.add(cat)
        session.commit()
        session.refresh(cat)

    # 3) now build & insert the MCQ
    mcq = MCQ(
        question_text=  payload.question_text,
        option_a=       payload.option_a,
        option_b=       payload.option_b,
        option_c=       payload.option_c,
        option_d=       payload.option_d,
        correct_answer= payload.correct_answer,
        explanation=    payload.explanation,
        category_id=    cat.id,
    )
    session.add(mcq)
    session.commit()
    session.refresh(mcq)
    return mcq



# ── 2a) Read: Paginated List ──────────────────────────────────────────────

@router.get("/", response_model=MCQPage)
def list_mcqs(
    *,
    session: SessionDep,
    category: Optional[str] = Query(None, description="filter by category slug"),
    page:     int          = Query(1, ge=1),
    per_page: int          = Query(10, ge=1, le=100),
):
    """
    Page through MCQs, optionally filtering by category slug.
    """
    filters = []
    if category:
        cat = session.exec(
            select(Category).where(Category.slug == category)
        ).one_or_none()
        if not cat:
            raise HTTPException(404, f"Category '{category}' not found")
        filters.append(MCQ.category_id == cat.id)

    total = session.exec(
        select(func.count(MCQ.id)).where(*filters)
    ).one()

    # empty
    if total == 0:
        return MCQPage(
            pagination=Pagination(
                total_items=0, total_pages=0,
                current_page=page, per_page=per_page,
                has_next_page=False, has_prev_page=False
            ),
            data=[]
        )

    # fetch the slice
    stmt = (
        select(MCQ).where(*filters)
        .order_by(desc(MCQ.id))
        .offset((page-1)*per_page).limit(per_page)
    )
    items = session.exec(stmt).all()
    total_pages = ceil(total / per_page)

    return MCQPage(
        pagination=Pagination(
            total_items=   total,
            total_pages=   total_pages,
            current_page=  page,
            per_page=      per_page,
            has_next_page= page < total_pages,
            has_prev_page= page > 1,
        ),
        data=items
    )


# ── 2b) Read: Single MCQ ─────────────────────────────────────────────────

@router.get("/{mcq_id}", response_model=MCQ)
def get_mcq(mcq_id: int, session: SessionDep):
    """
    Fetch one MCQ by its ID.
    """
    mcq = session.get(MCQ, mcq_id)
    if not mcq:
        raise HTTPException(404, "MCQ not found")
    return mcq


# ── 3) Update an MCQ ──────────────────────────────────────────────────────

@router.put("/{mcq_id}", response_model=MCQ)
def update_mcq(
    mcq_id:    int,
    payload:   MCQUpdate,
    session:   SessionDep,
):
    """
    Update an existing MCQ.  Optional `payload.category_slug` reassigns category.
    """
    mcq = session.get(MCQ, mcq_id)
    if not mcq:
        raise HTTPException(404, "MCQ not found")

    # reassign category?
    if payload.category_slug:
        cat = session.exec(
            select(Category).where(Category.slug == payload.category_slug)
        ).one_or_none()
        if not cat:
            raise HTTPException(404, f"Category '{payload.category_slug}' not found")
        mcq.category_id = cat.id

    # apply other updates
    updates = payload.model_dump(exclude_unset=True)
    for field, val in updates.items():
        if field != "category_slug":
            setattr(mcq, field, val)

    session.add(mcq)
    session.commit()
    session.refresh(mcq)
    return mcq


# ── 4) Delete an MCQ ──────────────────────────────────────────────────────

@router.delete("/{mcq_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mcq(mcq_id: int, session: SessionDep):
    """
    Delete an MCQ by ID.
    """
    mcq = session.get(MCQ, mcq_id)
    if not mcq:
        raise HTTPException(404, "MCQ not found")

    session.delete(mcq)
    session.commit()
    return None


# ── 5) Bulk Create ───────────────────────────────────────────────────────

@router.post("/bulk", response_model=BulkMCQCreateResponse, status_code=201)
def bulk_create_mcqs(payload: MCQBulkCreate, session: SessionDep):
    """
    Insert many MCQs at once.  Each MCQCreate must include `category_slug`.
    """
    created: List[MCQ]    = []
    counts:  Dict[str,int]= {}

    for entry in payload.mcqs:
        cat = session.exec(
            select(Category).where(Category.slug == entry.category_slug)
        ).one_or_none()
        if not cat:
            raise HTTPException(404, f"Category '{entry.category_slug}' not found")

        mcq = MCQ(
            question_text=  entry.question_text,
            option_a=       entry.option_a,
            option_b=       entry.option_b,
            option_c=       entry.option_c,
            option_d=       entry.option_d,
            correct_answer= entry.correct_answer,
            explanation=    entry.explanation,
            category_id=    cat.id,
        )
        session.add(mcq)
        created.append(mcq)
        counts[entry.category_slug] = counts.get(entry.category_slug, 0) + 1

    session.commit()
    for mcq in created:
        session.refresh(mcq)

    return BulkMCQCreateResponse(
        mcqs=            created,
        total_added=     len(created),
        category_counts= counts,
        total_categories=len(counts),
    )


# ── 6) Stats ─────────────────────────────────────────────────────────────

@router.get("/questions/statistics", response_model=StatsResponse)
def get_stats(session: SessionDep):
    total = session.exec(select(func.count(MCQ.id))).one()
    rows = session.exec(
        select(Category.slug, func.count(MCQ.id))
        .join(MCQ, MCQ.category_id == Category.id)
        .group_by(Category.slug)
    ).all()
    counts = {slug: cnt for slug, cnt in rows}
    return StatsResponse(
        total_questions= total,
        category_counts= counts,
        total_categories= len(counts),
    )


# ── 7) Repeated Questions ─────────────────────────────────────────────────

@router.get("/questions/repeated", response_model=List[RepeatedQuestion])
def get_repeated(
    session: SessionDep,
    threshold: int = Query(2, ge=1, description="min occurrences"),
):
    """
    List all questions that appear at least `threshold` times.
    """
    rows = session.exec(
        select(
            MCQ.question_text,
            func.count(MCQ.id).label("cnt")
        )
        .group_by(MCQ.question_text)
        .having(func.count(MCQ.id) >= threshold)
        .order_by(desc("cnt")) 
    ).all()

    return [RepeatedQuestion(question_text=qt, count=cnt) for qt, cnt in rows]


# ── 8) Random Sample ────────────────────────────────────────────────────

@router.get("/q/random", response_model=List[MCQ])
def get_random(
    session: SessionDep,
    count:   int          = Query(5, ge=1, le=100),
):
    """
    Fetch a random sample of `count` MCQs.
    """
    # pull all IDs
    all_ids: List[int] = session.exec(select(MCQ.id)).all()
    if not all_ids:
        return []

    chosen = random.sample(all_ids, min(count, len(all_ids)))
    return session.exec(select(MCQ).where(MCQ.id.in_(chosen))).all()
