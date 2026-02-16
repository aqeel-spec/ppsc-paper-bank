from typing import List, Optional, Dict, Literal
from datetime import datetime
from math import ceil
import random

from fastapi import APIRouter, HTTPException, status, Query, Request, HTTPException
from pydantic import BaseModel
from sqlmodel import SQLModel, Field, select, func, desc, Relationship
from sqlalchemy import or_
from .sessionDep import SessionDep  # yields an AsyncSession
# from mcq import MCQ as MCQModel
from app.models import PaperModel, PaperMCQ, MCQ as MCQModel, AnswerOption, Category, MCQRead
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse
from io import BytesIO
import importlib
from pathlib import Path
import re
from urllib.parse import urlparse, unquote

# PDF generation:
# - Prefer WeasyPrint when available (best CSS support)
# - Fallback to xhtml2pdf on Windows (no GTK dependency)
try:
    _weasyprint = importlib.import_module("weasyprint")
    HTML = getattr(_weasyprint, "HTML")
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False
    HTML = None

try:
    from xhtml2pdf import pisa
    XHTML2PDF_AVAILABLE = True
except ImportError:
    XHTML2PDF_AVAILABLE = False
    pisa = None


_STATIC_DIR = Path("app/utils/static").resolve()


def _xhtml2pdf_link_callback(uri: str, rel: str | None = None) -> str:
    """Resolve /static/... URIs to local filesystem paths for xhtml2pdf."""
    if uri.startswith("/static/"):
        target = (_STATIC_DIR / uri.removeprefix("/static/")).resolve()
        return str(target)

    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return unquote(parsed.path)

    # For any other relative paths, return as-is. (Remote http(s) resources may
    # or may not be fetched by xhtml2pdf depending on environment.)
    return uri


def _render_pdf_from_html(html: str, request: Request) -> BytesIO:
    """Render PDF bytes from HTML using WeasyPrint or xhtml2pdf."""
    pdf_io = BytesIO()

    if WEASYPRINT_AVAILABLE and HTML is not None:
        HTML(string=html, base_url=str(request.base_url)).write_pdf(pdf_io)
        pdf_io.seek(0)
        return pdf_io

    if XHTML2PDF_AVAILABLE and pisa is not None:
        # xhtml2pdf uses ReportLab; on Windows the CSS @font-face path handling
        # can trigger temp-file permission errors. Register the Urdu font directly
        # and strip @font-face blocks from the HTML.
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            font_path = (_STATIC_DIR / "fonts" / "NotoNastaliqUrdu-Regular.ttf").resolve()
            if font_path.exists():
                pdfmetrics.registerFont(TTFont("NotoNastaliqUrdu", str(font_path)))

            prepared = re.sub(r"@font-face\s*\{.*?\}\s*", "", html, flags=re.S | re.I)
            prepared = prepared.replace("Noto Nastaliq Urdu", "NotoNastaliqUrdu")

            status = pisa.CreatePDF(
                prepared,
                dest=pdf_io,
                encoding="UTF-8",
                link_callback=_xhtml2pdf_link_callback,
            )
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="PDF generation failed (xhtml2pdf). Install WeasyPrint+GTK for best results, or simplify the PDF template CSS.",
            )

        if status.err:
            raise HTTPException(
                status_code=503,
                detail="PDF generation failed (xhtml2pdf). The template/CSS may contain unsupported features.",
            )

        pdf_io.seek(0)
        return pdf_io

    raise HTTPException(
        status_code=503,
        detail="PDF generation unavailable. Install either WeasyPrint (requires GTK on Windows) or xhtml2pdf.",
    )


# --- Response schemas ---
class PaperResponse(BaseModel):
    id: int
    created_at: datetime
    category_id: Optional[int] = None
    category_slug: Optional[str] = None
    mcqs: List[MCQRead]

    class Config:
        from_attributes = True


class PaperItem(BaseModel):
    length:        int
    created_at:    datetime
    view_url:      str
    pdf_q_url:     str
    pdf_a_url:     str

    class Config:
        from_attributes = True

class PapersListResponse(BaseModel):
    total_papers:  int
    total_pages:   int
    page:          int
    per_page:      int
    # keyed dict: "paper_<id>" → PaperItem
    papers:        Dict[str, PaperItem]


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
        n = len(p.paper_mcqs)
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
    difficulty: str = Query("medium", description="Paper difficulty (default: medium)"),
    category_slug: Optional[str] = Query(None, description="Filter by category slug"),
    category_id: Optional[int] = Query(None, description="Filter by category id"),
):
    if category_slug and category_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use either category_slug OR category_id, not both.",
        )

    selected_category_id: Optional[int] = None
    selected_category_slug: Optional[str] = None
    if category_slug:
        cat = session.exec(select(Category).where(Category.slug == category_slug)).one_or_none()
        if not cat:
            raise HTTPException(404, f"Category '{category_slug}' not found")
        selected_category_id = cat.id
        selected_category_slug = cat.slug
    elif category_id is not None:
        cat = session.get(Category, category_id)
        if not cat:
            raise HTTPException(404, f"Category id '{category_id}' not found")
        selected_category_id = cat.id
        selected_category_slug = cat.slug

    # 1) find all question_texts with at least `threshold` repeats
    freq_stmt = (
        select(
            MCQModel.question_text,
            func.count(MCQModel.id).label("cnt")
        )
        .where(*( [MCQModel.category_id == selected_category_id] if selected_category_id is not None else []))
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
    paper = PaperModel(difficulty=difficulty)
    session.add(paper)
    session.commit()
    session.refresh(paper)

    # 4) link each MCQ to this paper
    mcqs: List[MCQModel] = []
    for question_text in batch:
        mcq = session.exec(
            select(MCQModel)
            .where(
                MCQModel.question_text == question_text,
                *( [MCQModel.category_id == selected_category_id] if selected_category_id is not None else []),
            )
            .order_by(desc(MCQModel.id))
        ).first()
        session.add(PaperMCQ(paper_id=paper.id, mcq_id=mcq.id))
        mcqs.append(mcq)

    session.commit()

    return PaperResponse(
        id=paper.id,
        created_at=paper.created_at,
        category_id=selected_category_id,
        category_slug=selected_category_slug,
        mcqs=[MCQRead.model_validate(m) for m in mcqs]
    )


class PaperGenerateRequest(BaseModel):
    # 1) Category selection
    # If not provided, generation is "generic" across all categories.
    category_slug: Optional[str] = None
    category_id: Optional[int] = None

    # 2) Year filter (best-effort): matched against category name/slug.
    year: Optional[int] = None

    # 4) Subject-specific (best-effort): matched against category name/slug.
    subject: Optional[str] = None

    # 5) Post-related (best-effort): matched against category name/slug.
    post: Optional[str] = None

    # 3) Repeated questions criteria (optional): minimum times a question_text repeats.
    min_repeats: Optional[int] = Field(default=None, ge=1)

    # How many MCQs to include
    size: int = Field(default=100, ge=1)

    # Difficulty (optional): defaults to medium
    difficulty: str = "medium"

    # Optional paper metadata
    title: Optional[str] = None
    paper_type: Optional[str] = None
    tags: Optional[str] = None


def _build_generated_title(payload: PaperGenerateRequest) -> str:
    parts: List[str] = ["Generated Paper"]

    if payload.category_slug:
        parts.append(f"Category={payload.category_slug}")
    if payload.category_id is not None:
        parts.append(f"CategoryId={payload.category_id}")
    if payload.year is not None:
        parts.append(f"Year={payload.year}")
    if payload.subject:
        parts.append(f"Subject={payload.subject}")
    if payload.post:
        parts.append(f"Post={payload.post}")
    if payload.min_repeats is not None:
        parts.append(f"MinRepeats={payload.min_repeats}")
    if payload.difficulty:
        parts.append(f"Difficulty={payload.difficulty}")

    return " | ".join(parts)


def _resolve_category_ids_for_generation(session: SessionDep, payload: PaperGenerateRequest) -> Optional[List[int]]:
    """Return a list of category IDs to filter MCQs by, or None for 'all categories'."""

    if payload.category_slug and payload.category_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use either category_slug OR category_id, not both.",
        )

    if payload.category_id is not None:
        cat = session.get(Category, payload.category_id)
        if not cat:
            raise HTTPException(404, f"Category id '{payload.category_id}' not found")
        return [cat.id]

    if payload.category_slug:
        cat = session.exec(select(Category).where(Category.slug == payload.category_slug)).one_or_none()
        if not cat:
            raise HTTPException(404, f"Category '{payload.category_slug}' not found")
        return [cat.id]

    # If no criteria that can map to category exists, default to generic (all categories)
    if payload.year is None and not payload.subject and not payload.post:
        return None

    stmt = select(Category.id)
    filters = []

    if payload.year is not None:
        year_token = str(payload.year)
        filters.append(or_(Category.name.ilike(f"%{year_token}%"), Category.slug.ilike(f"%{year_token}%")))

    if payload.subject:
        subject = payload.subject.strip()
        filters.append(or_(Category.name.ilike(f"%{subject}%"), Category.slug.ilike(f"%{subject}%")))

    if payload.post:
        post = payload.post.strip()
        filters.append(or_(Category.name.ilike(f"%{post}%"), Category.slug.ilike(f"%{post}%")))

    if filters:
        stmt = stmt.where(*filters)

    category_ids = list(session.exec(stmt).all())
    if not category_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No categories matched the provided criteria (year/subject/post).",
        )
    return category_ids


@router.post(
    "/generate",
    response_model=PaperResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a paper from optional criteria",
    description=(
        "Creates a paper by selecting distinct questions from the MCQ bank. "
        "All criteria are optional. If no category/year/subject/post is provided, "
        "generation defaults to a generic selection across all available categories."
    ),
)
def generate_paper(payload: PaperGenerateRequest, session: SessionDep):
    category_ids = _resolve_category_ids_for_generation(session, payload)

    selected_category_id: Optional[int] = None
    selected_category_slug: Optional[str] = None
    if payload.category_slug:
        cat = session.exec(select(Category).where(Category.slug == payload.category_slug)).one_or_none()
        if not cat:
            raise HTTPException(404, f"Category '{payload.category_slug}' not found")
        selected_category_id = cat.id
        selected_category_slug = cat.slug
    elif payload.category_id is not None:
        cat = session.get(Category, payload.category_id)
        if not cat:
            raise HTTPException(404, f"Category id '{payload.category_id}' not found")
        selected_category_id = cat.id
        selected_category_slug = cat.slug

    mcq_filters = []
    if category_ids is not None:
        mcq_filters.append(MCQModel.category_id.in_(category_ids))

    # Build a subquery that picks a representative MCQ per question_text.
    # - If min_repeats is set: only include questions that repeat >= min_repeats within the filtered set.
    # - Otherwise: include any distinct question_text (latest MCQ id wins).
    if payload.min_repeats is not None:
        rep_stmt = (
            select(
                func.min(MCQModel.id).label("mcq_id"),
                MCQModel.question_text.label("question_text"),
                func.count(MCQModel.id).label("cnt"),
            )
            .where(*mcq_filters)
            .group_by(MCQModel.question_text)
            .having(func.count(MCQModel.id) >= payload.min_repeats)
            .order_by(desc("cnt"))
        )
    else:
        rep_stmt = (
            select(
                func.max(MCQModel.id).label("mcq_id"),
                MCQModel.question_text.label("question_text"),
                func.count(MCQModel.id).label("cnt"),
            )
            .where(*mcq_filters)
            .group_by(MCQModel.question_text)
            .order_by(desc(func.max(MCQModel.id)))
        )

    rep_subq = rep_stmt.subquery()

    # Deterministic selection (not random):
    # - if min_repeats: highest repeat count first
    # - else: newest questions first (by MCQ id)
    selection_stmt = select(MCQModel).join(rep_subq, rep_subq.c.mcq_id == MCQModel.id)
    if payload.min_repeats is not None:
        selection_stmt = selection_stmt.order_by(desc(rep_subq.c.cnt), desc(MCQModel.id))
    else:
        selection_stmt = selection_stmt.order_by(desc(MCQModel.id))
    selection_stmt = selection_stmt.limit(payload.size)

    selected_mcqs: List[MCQModel] = list(session.exec(selection_stmt).all())

    if len(selected_mcqs) < payload.size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Not enough questions to build a paper of size={payload.size}. "
                "Try reducing size or relaxing filters/min_repeats."
            ),
        )

    paper = PaperModel(
        title=payload.title or _build_generated_title(payload),
        year=payload.year,
        paper_type=payload.paper_type,
        tags=payload.tags,
        difficulty=payload.difficulty or "medium",
    )
    session.add(paper)
    session.commit()
    session.refresh(paper)

    for mcq in selected_mcqs:
        session.add(PaperMCQ(paper_id=paper.id, mcq_id=mcq.id))

    session.commit()

    return PaperResponse(
        id=paper.id,
        created_at=paper.created_at,
        category_id=selected_category_id,
        category_slug=selected_category_slug,
        mcqs=[MCQRead.model_validate(m) for m in selected_mcqs],
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
    difficulty: str = Query("medium", description="Paper difficulty (default: medium)"),
    category_slug: Optional[str] = Query(None, description="Filter by category slug"),
    category_id: Optional[int] = Query(None, description="Filter by category id"),
):
    papers: List[PaperResponse] = []
    for _ in range(count):
        paper = create_paper(
            session,
            threshold=threshold,
            size=size,
            difficulty=difficulty,
            category_slug=category_slug,
            category_id=category_id,
        )
        papers.append(paper)
    return papers


# get paper details at specific id
@router.get("/{paper_id}", response_model=PaperResponse, summary="Fetch one paper")
def get_paper(paper_id: int, session: SessionDep):
    paper = session.exec(select(PaperModel).where(PaperModel.id == paper_id)).one_or_none()
    if not paper:
        raise HTTPException(404, f"Paper {paper_id} not found")
    mcqs = [link.mcq for link in paper.paper_mcqs]
    return PaperResponse(
        id=paper.id,
        created_at=paper.created_at,
        mcqs=[MCQRead.model_validate(m) for m in mcqs],
    )


class PaperMCQsResponse(BaseModel):
    paper_id: int
    total_mcqs: int
    limit: int
    offset: int
    mcqs: List[MCQModel]


class PaperMCQItem(BaseModel):
    id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    category_id: int
    created_at: datetime
    updated_at: datetime
    correct_answer: Optional[AnswerOption] = None
    explanation: Optional[str] = None

    class Config:
        from_attributes = True


class PaperMCQsModeResponse(BaseModel):
    paper_id: int
    mode: Literal["quiz", "read"]
    total_mcqs: int
    limit: int
    offset: int
    show_answers: bool
    show_explanations: bool
    mcqs: List[PaperMCQItem]


@router.get(
    "/{paper_id}/mcqs",
    response_model=PaperMCQsResponse,
    summary="Fetch paper MCQs (paginated)",
    description="Returns MCQs for a paper using limit/offset pagination. Default limit=10 for quiz flows.",
)
def get_paper_mcqs(
    paper_id: int,
    session: SessionDep,
    limit: int = Query(10, ge=1, le=100, description="Number of MCQs to return"),
    offset: int = Query(0, ge=0, description="Number of MCQs to skip"),
):
    paper = session.exec(select(PaperModel).where(PaperModel.id == paper_id)).one_or_none()
    if not paper:
        raise HTTPException(404, f"Paper {paper_id} not found")

    total_mcqs = session.exec(
        select(func.count(PaperMCQ.mcq_id)).where(PaperMCQ.paper_id == paper_id)
    ).one()

    mcqs = session.exec(
        select(MCQModel)
        .join(PaperMCQ, PaperMCQ.mcq_id == MCQModel.id)
        .where(PaperMCQ.paper_id == paper_id)
        .order_by(MCQModel.id)
        .offset(offset)
        .limit(limit)
    ).all()

    return PaperMCQsResponse(
        paper_id=paper_id,
        total_mcqs=total_mcqs,
        limit=limit,
        offset=offset,
        mcqs=mcqs,
    )


@router.get(
    "/{paper_id}/with-mcqs",
    response_model=PaperMCQsModeResponse,
    summary="Fetch paper MCQs in read/quiz mode (paginated)",
    description=(
        "Use mode=quiz for quiz UI (hides answers/explanations). "
        "Use mode=read for study/read UI (shows answers by default; explanations optional)."
    ),
)
def get_paper_mcqs_mode(
    paper_id: int,
    session: SessionDep,
    mode: Literal["quiz", "read"] = Query("quiz", description="quiz hides answers; read shows answers"),
    limit: int = Query(10, ge=1, le=100, description="Number of MCQs to return"),
    offset: int = Query(0, ge=0, description="Number of MCQs to skip"),
    show_answers: Optional[bool] = Query(None, description="Override default answer visibility"),
    show_explanations: bool = Query(False, description="In read mode, include explanations"),
):
    paper = session.exec(select(PaperModel).where(PaperModel.id == paper_id)).one_or_none()
    if not paper:
        raise HTTPException(404, f"Paper {paper_id} not found")

    total_mcqs = session.exec(
        select(func.count(PaperMCQ.mcq_id)).where(PaperMCQ.paper_id == paper_id)
    ).one()

    mcqs: List[MCQModel] = session.exec(
        select(MCQModel)
        .join(PaperMCQ, PaperMCQ.mcq_id == MCQModel.id)
        .where(PaperMCQ.paper_id == paper_id)
        .order_by(MCQModel.id)
        .offset(offset)
        .limit(limit)
    ).all()

    # Mode rules:
    # - quiz: never return answers/explanations by default
    # - read: return answers by default; explanations optional
    effective_show_answers = show_answers if show_answers is not None else (mode == "read")
    effective_show_explanations = (mode == "read") and show_explanations

    out: List[PaperMCQItem] = []
    for m in mcqs:
        out.append(
            PaperMCQItem(
                id=m.id,
                question_text=m.question_text,
                option_a=m.option_a,
                option_b=m.option_b,
                option_c=m.option_c,
                option_d=m.option_d,
                category_id=m.category_id,
                created_at=m.created_at,
                updated_at=m.updated_at,
                correct_answer=m.correct_answer if effective_show_answers else None,
                explanation=m.explanation if effective_show_explanations else None,
            )
        )

    return PaperMCQsModeResponse(
        paper_id=paper_id,
        mode=mode,
        total_mcqs=total_mcqs,
        limit=limit,
        offset=offset,
        show_answers=effective_show_answers,
        show_explanations=effective_show_explanations,
        mcqs=out,
    )



# ─── 3) VIEW IN BROWSER (HTML) ─────────────────────────────────────────────
@router.get("/{paper_id}/view", response_class=HTMLResponse)
def view_paper(request: Request, paper_id: int, session: SessionDep):
    paper = session.get(PaperModel, paper_id) or HTTPException(404)
    mcqs  = [l.mcq for l in paper.paper_mcqs]
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
    mcqs  = [l.mcq for l in paper.paper_mcqs]

    tpl = "paper_detail.html" if show_answers else "paper_noanswers.html"
    html = templates.get_template(tpl).render(
        paper_id=paper.id,
        created_at=paper.created_at,
        mcqs=mcqs,
    )

    pdf_io = _render_pdf_from_html(html, request)
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
            "mcqs":       [link.mcq for link in p.paper_mcqs],
        }
        for p in papers
    ]

    tpl_name = "all_papers_with_answers.html" if show_answers else "all_papers_q_only.html"
    html_str = templates.get_template(tpl_name).render(papers=all_ctx, request=request)

    pdf_io = _render_pdf_from_html(html_str, request)

    return StreamingResponse(
        pdf_io,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=all_papers.pdf"},
    )