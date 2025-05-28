import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select,desc , func
from pydantic import BaseModel
from typing import Dict

import random
from math import ceil
from app.models.mcq import MCQ, MCQCreate, MCQUpdate, MCQBulkCreate, Category
from .sessionDep import SessionDep  # yields an AsyncSession

router = APIRouter(prefix="/mcqs")

class Pagination(BaseModel):
    total_items: int
    total_pages: int
    current_page: int
    per_page: int
    has_next_page: bool
    has_prev_page: bool

class BulkMCQCreateResponse(BaseModel):
    mcqs: List[MCQ]
    total_added: int
    category_counts: Dict[str, int]
    total_categories: int

class MCQPage(BaseModel):
    pagination: Pagination
    data: List[MCQ]
    
class StatsResponse(BaseModel):
    total_questions: int
    category_counts: Dict[str, int]
    total_categories: int

class RepeatedQuestion(BaseModel):
    question_text: str
    count: int



def _maybe_await(result):
    """
    If result is a coroutine, await it; otherwise return it directly.
    """
    return result if not asyncio.iscoroutine(result) else asyncio.ensure_future(result)


@router.post("/", response_model=MCQ, status_code=status.HTTP_201_CREATED)
async def create_mcq(
    mcq_in: MCQCreate,
    session: SessionDep,
):
    try:
        db_mcq = MCQ.model_validate(mcq_in)
        session.add(db_mcq)
        session.commit()
        session.refresh(db_mcq)
        return db_mcq

    except ValidationError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ve.errors(),
        )
    except SQLAlchemyError as sae:
        await _maybe_await(session.rollback())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {sae}",
        )
    except Exception as e:
        await _maybe_await(session.rollback())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {e}",
        )




@router.get("/", response_model=MCQPage)
async def get_mcqs(
    *,
    session: SessionDep,
    category: Optional[Category] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
) -> MCQPage:
    # --- build filter list ---
    filters = []
    if category is not None:
        filters.append(MCQ.category == category)

    # --- total count ---
    count_stmt = select(func.count(MCQ.id))
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = session.exec(count_stmt).first()

    # --- empty shortcut ---
    if total == 0:
        empty_pagination = Pagination(
            total_items=0,
            total_pages=0,
            current_page=page,
            per_page=per_page,
            has_next_page=False,
            has_prev_page=False,
        )
        return MCQPage(pagination=empty_pagination, data=[])

    # --- fetch a page of rows ---
    stmt = (
        select(MCQ)
        .where(*filters) if filters else select(MCQ)
    )
    stmt = (
        stmt.order_by(desc(MCQ.id))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = session.exec(stmt)
    items = result.all()

    # --- build pagination metadata ---
    total_pages = ceil(total / per_page)
    pagination = Pagination(
        total_items=total,
        total_pages=total_pages,
        current_page=page,
        per_page=per_page,
        has_next_page=page < total_pages,
        has_prev_page=page > 1,
    )

    return MCQPage(pagination=pagination, data=items)

@router.get("/{mcq_id}", response_model=MCQ)
async def get_mcq(
    mcq_id: int,
    session: SessionDep,
):
    result = session.exec(select(MCQ).where(MCQ.id == mcq_id))
    mcq = result.first()
    if not mcq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCQ not found")
    return mcq


@router.put("/{mcq_id}", response_model=MCQ)
async def update_mcq(
    mcq_id: int,
    mcq_update: MCQUpdate,
    session: SessionDep,
):
    try:
        result = session.exec(select(MCQ).where(MCQ.id == mcq_id))
        db_mcq = result.first()
        if not db_mcq:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCQ not found")

        update_data = mcq_update.model_dump(exclude_unset=True)
        for field, val in update_data.items():
            setattr(db_mcq, field, val)

        session.add(db_mcq)
        _maybe_await(session.commit())
        _maybe_await(session.refresh(db_mcq))
        return db_mcq

    except ValidationError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ve.errors(),
        )
    except SQLAlchemyError as sae:
        await _maybe_await(session.rollback())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {sae}",
        )
    except Exception as e:
        await _maybe_await(session.rollback())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {e}",
        )


@router.delete("/{mcq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcq(
    mcq_id: int,
    session: SessionDep,
):
    try:
        result = session.exec(select(MCQ).where(MCQ.id == mcq_id))
        db_mcq = result.first()
        if not db_mcq:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCQ not found")

        session.delete(db_mcq)
        _maybe_await(session.commit())
        return {"message": "MCQ deleted successfully"}
    except SQLAlchemyError as sae:
        await _maybe_await(session.rollback())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {sae}",
        )
    except Exception as e:
        await _maybe_await(session.rollback())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {e}",
        )


@router.post(
    "/bulk",
    response_model=BulkMCQCreateResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_mcqs_bulk(
    payload: MCQBulkCreate,
    session: SessionDep,
):
    try:
        # Convert incoming items to DB models
        db_mcqs = [MCQ.model_validate(item) for item in payload.mcqs]
        session.add_all(db_mcqs)
        _maybe_await(session.commit())

        # Refresh to get generated fields (e.g. IDs)
        for obj in db_mcqs:
            _maybe_await(session.refresh(obj))

        # Compute counts
        total_added = len(db_mcqs)
        category_counts: Dict[str, int] = {}
        for item in payload.mcqs:
            cat = getattr(item, "category", None)
            if cat:
                category_counts[cat] = category_counts.get(cat, 0) + 1

        # Number of distinct categories
        total_categories = len(category_counts)

        # Return both data and stats
        return BulkMCQCreateResponse(
            total_added=total_added,
            category_counts=category_counts,
            total_categories=total_categories,
            mcqs=db_mcqs
        )

    except ValidationError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ve.errors(),
        )
    except SQLAlchemyError as sae:
        _maybe_await(session.rollback())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {sae}",
        )
    except Exception as e:
        _maybe_await(session.rollback())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {e}",
        )


@router.get("/category/{category}", response_model=List[MCQ])
async def get_mcqs_by_category(
    category: Category,
    session: SessionDep,
):
    result = session.exec(select(MCQ).where(MCQ.category == category))
    return result.all()


# --- Analytics Endpoints (placed before dynamic id route to avoid conflicts) ---

@router.get("/stats/papers", response_model=StatsResponse)
def get_stats(
        session: SessionDep,
    ):
    """
    Returns overall stats: total question count and breakdown by category.
    """
    total = session.exec(select(func.count(MCQ.id))).first()
    counts = session.exec(
        select(MCQ.category, func.count(MCQ.id)).group_by(MCQ.category)
    ).all()
    category_counts = {cat: cnt for cat, cnt in counts}
    return StatsResponse(
        total_questions=total,
        category_counts=category_counts,
        total_categories=len(category_counts)
    )

@router.get("/analytics/repeated", response_model=List[RepeatedQuestion])
async def get_most_repeated(
    session: SessionDep,
    top_n: int = Query(10, ge=1, le=100),
):
    """
    Returns the top N most frequent questions in the bank.
    """
    counts = session.exec(
        select(MCQ.question_text, func.count(MCQ.id))
        .group_by(MCQ.question_text)
        .order_by(desc(func.count(MCQ.id)))
        .limit(top_n)
    ).all()
    return [RepeatedQuestion(question_text=text, count=cnt) for text, cnt in counts]

@router.get("/random/questions", response_model=List[MCQ])
async def get_random_questions(
    session: SessionDep,
    count: int = Query(5, ge=1, le=50),
):
    """
    Fetches a random selection of questions from the bank.
    """
    # Pull all IDs (List[int])
    all_ids: List[int] = session.exec(select(MCQ.id)).all()
    # Sample directly since exec returns ints
    chosen_ids = random.sample(all_ids, min(count, len(all_ids)))
    result = session.exec(select(MCQ).where(MCQ.id.in_(chosen_ids)))
    return result.all()