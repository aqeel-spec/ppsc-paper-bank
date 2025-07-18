from typing import List, Optional, Dict
from datetime import datetime
from math import ceil
import random

from fastapi import APIRouter, HTTPException, status, Query, Request, HTTPException
from pydantic import BaseModel
from sqlmodel import SQLModel, Field, select, func, desc, Relationship
from .sessionDep import SessionDep  # yields an AsyncSession
# from mcq import MCQ as MCQModel
from app.models import PaperModel, PaperMCQ, MCQ as MCQModel
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse
from io import BytesIO
from weasyprint import HTML


# --- Response schemas ---
class PaperResponse(BaseModel):
    id: int
    created_at: datetime
    mcqs: List[MCQModel]
    
class PaperItem(BaseModel):
    length:        int
    created_at:    datetime
    view_url:      str
    pdf_q_url:     str
    pdf_a_url:     str

    class Config:
        orm_mode = True

class PapersListResponse(BaseModel):
    total_papers:  int
    total_pages:   int
    page:          int
    per_page:      int
    # keyed dict: "paper_<id>" → PaperItem
    papers:        Dict[str, PaperItem]


class PaperResponse(BaseModel):
    id: int
    created_at: datetime
    mcqs: List[MCQModel]

    class Config:
        orm_mode = True




router = APIRouter(prefix="/papers")

# point this at wherever you keep your templates
templates = Jinja2Templates(directory="app/utils")  # points at app/utils


# ─── 1) LIST ALL PAPERS (JSON) ──────────────────────────────────────────────

# download paper one by one 
# or view in browser
# download without answers
# download with answers
@router.get("/", response_model=PapersListResponse)
def list_papers(
    session: SessionDep,
    page:     int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    total_papers = session.exec(select(func.count(PaperModel.id))).one()
    total_pages  = ceil(total_papers / per_page)
    papers = session.exec(
        select(PaperModel)
        .order_by(desc(PaperModel.id))
        .offset((page-1)*per_page)
        .limit(per_page)
    ).all()

    out = {}
    for p in papers:
        n = len(p.mcq_links)
        out[f"paper_{p.id}"] = PaperItem(
            length=     n,
            created_at= p.created_at.isoformat(),
            view_url=   f"/papers/{p.id}/view",
            pdf_q_url=  f"/papers/{p.id}/pdf?show_answers=false",
            pdf_a_url=  f"/papers/{p.id}/pdf?show_answers=true",
        )

    return PapersListResponse(
        total_papers= total_papers,
        total_pages=  total_pages,
        page=         page,
        per_page=     per_page,
        papers=       out,
    )



@router.post(
    "/",
    response_model=PaperResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new paper",
    description=(
        "Creates a new paper by selecting the next `size` distinct questions "
        "that have appeared at least `threshold` times, ensuring no overlap "
        "with existing papers."
    )
)
def create_paper(
    session: SessionDep,
    threshold: int = Query(10, ge=1, description="Minimum times a question must repeat"),
    size:      int = Query(100, ge=1, description="Number of questions in the paper"),
):
    # 1) find all question_texts with at least `threshold` repeats
    freq_stmt = (
        select(
            MCQModel.question_text,
            func.count(MCQModel.id).label("cnt")
        )
        .group_by(MCQModel.question_text)
        .having(func.count(MCQModel.id) >= threshold)
        .order_by(desc("cnt"))
    )
    freq = session.exec(freq_stmt).all()
    texts = [text for text, _ in freq]

    # 2) calculate offset based on how many papers exist
    total_papers = session.exec(select(func.count(PaperModel.id))).one()
    offset = total_papers * size
    batch = texts[offset : offset + size]
    if len(batch) < size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough repeated questions left to build a new paper."
        )

    # 3) create the PaperModel record
    paper = PaperModel()
    session.add(paper)
    session.commit()
    session.refresh(paper)

    # 4) link each MCQ to this paper
    mcqs: List[MCQModel] = []
    for question_text in batch:
        mcq = session.exec(
            select(MCQModel).where(MCQModel.question_text == question_text)
        ).first()
        session.add(PaperMCQ(paper_id=paper.id, mcq_id=mcq.id))
        mcqs.append(mcq)

    session.commit()

    return PaperResponse(
        id=paper.id,
        created_at=paper.created_at,
        mcqs=mcqs
    )


@router.post(
    "/bulk",
    response_model=List[PaperResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate multiple papers",
    description="Generate `count` papers in a row using the same threshold/size logic."
)
def create_bulk_papers(
    session: SessionDep,
    count:     int = Query(50, ge=1, description="How many papers to generate"),
    threshold: int = Query(10, ge=1, description="Min repeats to include"),
    size:      int = Query(100, ge=1, description="Questions per paper"),
):
    papers: List[PaperResponse] = []
    for _ in range(count):
        paper = create_paper(session, threshold=threshold, size=size)
        papers.append(paper)
    return papers


# get paper details at specific id
@router.get("/{paper_id}", response_model=PaperResponse, summary="Fetch one paper")
def get_paper(paper_id: int, session: SessionDep):
    paper = session.exec(select(PaperModel).where(PaperModel.id == paper_id)).one_or_none()
    if not paper:
        raise HTTPException(404, f"Paper {paper_id} not found")
    mcqs = [link.mcq for link in paper.mcq_links]
    return PaperResponse(id=paper.id, created_at=paper.created_at, mcqs=mcqs)



# ─── 3) VIEW IN BROWSER (HTML) ─────────────────────────────────────────────
@router.get("/{paper_id}/view", response_class=HTMLResponse)
def view_paper(request: Request, paper_id: int, session: SessionDep):
    paper = session.get(PaperModel, paper_id) or HTTPException(404)
    mcqs  = [l.mcq for l in paper.mcq_links]
    return templates.TemplateResponse(
        "paper_detail.html",
        {"request":request, "paper_id":paper_id, "created_at":paper.created_at, "mcqs":mcqs}
    )

@router.get("/{paper_id}/pdf")
def download_pdf(
    request:      Request,
    paper_id:     int,
    session:      SessionDep,
    show_answers: bool = Query(False, description="include answers?"),
):
    paper = session.get(PaperModel, paper_id) or HTTPException(404)
    mcqs  = [l.mcq for l in paper.mcq_links]

    tpl = "paper_detail.html" if show_answers else "paper_noanswers.html"
    html = templates.get_template(tpl).render(
        paper_id=paper.id,
        created_at=paper.created_at,
        mcqs=mcqs,
    )

    pdf_io = BytesIO()
    HTML(string=html, base_url=str(request.base_url)).write_pdf(pdf_io)
    pdf_io.seek(0)
    return StreamingResponse(
        pdf_io,
        media_type="application/pdf",
        headers={"Content-Disposition":f"attachment; filename=paper_{paper_id}.pdf"}
    )

# ─── 4) DOWNLOAD ALL PAPERS AS PDF ────────────────────────────────────────────
# --- download all as PDF (questions‐only or with answers)
@router.get(
    "/pdf/all",
    summary="Download ALL papers as a single PDF",
    response_class=StreamingResponse,
)
def download_all_papers_pdf(
    request: Request,
    session: SessionDep,
    show_answers: bool = Query(False, description="Include answers?"),
):
    papers = session.exec(select(PaperModel).order_by(PaperModel.id)).all()
    if not papers:
        raise HTTPException(404, "No papers found")

    # build your contexts
    all_ctx = [
        {
            "paper_id":   p.id,
            "created_at": p.created_at,
            "mcqs":       [link.mcq for link in p.mcq_links],
        }
        for p in papers
    ]

    tpl_name = "all_papers_with_answers.html" if show_answers else "all_papers_q_only.html"
    html_str = templates.get_template(tpl_name).render(papers=all_ctx, request=request)

    pdf_io = BytesIO()
    HTML(string=html_str, base_url=str(request.base_url)).write_pdf(pdf_io)
    pdf_io.seek(0)

    return StreamingResponse(
        pdf_io,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=all_papers.pdf"},
    )