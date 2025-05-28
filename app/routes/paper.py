from typing import List, Optional
from datetime import datetime
from math import ceil
import random

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from sqlmodel import SQLModel, Field, select, func, desc, Relationship
from .sessionDep import SessionDep  # yields an AsyncSession
# from mcq import MCQ as MCQModel
from app.models.mcq import PaperModel, PaperMCQ, MCQ as MCQModel


# --- Response schemas ---
class PaperResponse(BaseModel):
    id: int
    created_at: datetime
    mcqs: List[MCQModel]


router = APIRouter(prefix="/papers")

@router.post(
    "/",
    response_model=PaperResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_paper(
    session: SessionDep,
    threshold: int = Query(10, ge=1, description="Min repeats to include"),
    size: int      = Query(100, ge=1, description="Questions per paper"),
):
    """
    Create one paper by grabbing the next `size` distinct questions
    that have appeared at least `threshold` times,
    ensuring no overlap with papers already generated.
    """
    # 1) get all distinct question_texts with frequency >= threshold
    freq = session.exec(
        select(
            MCQModel.question_text,
            func.count(MCQModel.id).label("cnt")
        )
        .group_by(MCQModel.question_text)
        .having(func.count(MCQModel.id) >= threshold)
        .order_by(desc("cnt"))
    ).all()
    texts = [t for t, _ in freq]

    # 2) calculate offset based on how many papers exist
    existing = session.exec(select(func.count(PaperModel.id))).first()
    start = existing * size
    batch = texts[start : start + size]
    if len(batch) < size:
        raise HTTPException(
            status_code=400,
            detail="Not enough repeated questions left to build a new paper."
        )

    # 3) create the PaperModel record
    paper = PaperModel()
    session.add(paper)
    session.commit()
    session.refresh(paper)

    # 4) link MCQs to this paper
    mcqs: List[MCQModel] = []
    for text in batch:
        mcq = session.exec(
            select(MCQModel).where(MCQModel.question_text == text)
        ).first()
        session.add(PaperMCQ(paper_id=paper.id, mcq_id=mcq.id))
        mcqs.append(mcq)

    session.commit()
    return PaperResponse(id=paper.id, created_at=paper.created_at, mcqs=mcqs)


@router.post("/bulk", response_model=List[PaperResponse], status_code=status.HTTP_201_CREATED)
async def create_bulk_papers(
    session: SessionDep,
    count: int = Query(50, ge=1, description="How many papers to generate"),
    threshold: int = Query(10, ge=1, description="Min repeats to include"),
    size: int = Query(100, ge=1, description="Questions per paper")
):
    papers: List[PaperResponse] = []
    for _ in range(count):
        paper = await create_paper(session, threshold=threshold, size=size)
        papers.append(paper)
    return papers


@router.get("/", response_model=List[PaperResponse])
async def list_papers(
    session: SessionDep,
    page: int     = Query(1, ge=1),
    per_page: int = Query(1, ge=1, le=10),
):
    """
    Page through generated papers.  `page=1` → first paper, `page=2` → second, etc.
    Omitting page/per_page will return all papers in a single list.
    """
    total = session.exec(select(func.count(PaperModel.id))).first()
    total_pages = ceil(total / per_page)

    items = session.exec(
        select(PaperModel)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .order_by(desc(PaperModel.id))
    ).all()

    out: List[PaperResponse] = []
    for paper in items:
        linked_mcqs = [link.mcq for link in paper.mcq_links]
        out.append(PaperResponse(
            id=paper.id,
            created_at=paper.created_at,
            mcqs=linked_mcqs
        ))

    return out
