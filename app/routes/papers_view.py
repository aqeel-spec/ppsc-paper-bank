from math import ceil
from typing import List

from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.templating import Jinja2Templates
from sqlmodel import select, func, desc

from .sessionDep import SessionDep
from app.models.mcq import PaperModel

router = APIRouter(prefix="/views")
templates = Jinja2Templates(directory="app/utils")


@router.get("/papers", summary="HTML view of papers list")
def papers_list(
    request: Request,
    session: SessionDep,
    page:     int       = Query(1, ge=1),
    per_page: int       = Query(10, ge=1, le=100),
):
    # total count & pages
    total = session.exec(select(func.count(PaperModel.id))).one()
    total_pages = ceil(total / per_page) if per_page else 1

    # fetch this page
    stmt = (
        select(PaperModel)
        .order_by(desc(PaperModel.id))
        .offset((page-1) * per_page)
        .limit(per_page)
    )
    papers = session.exec(stmt).all()

    # build a simple list of dicts for the template
    papers_ctx: List[dict] = []
    for p in papers:
        mcqs = [ link.mcq for link in p.mcq_links ]
        papers_ctx.append({
            "id":          p.id,
            "created_at":  p.created_at,
            "length":      len(mcqs),
            # you'll need to implement /papers/{id}/pdf if you want real PDF downloads
            "pdf_url":     f"/papers/{p.id}/pdf",
        })

    return templates.TemplateResponse("temp1.html", {
        "request":      request,
        "api_base":     "/papers",
        "papers":       papers_ctx,
        "page":         page,
        "per_page":     per_page,
        "total_pages":  total_pages,
        "total_papers": total,
    })


@router.get("/papers/{paper_id}", summary="HTML view of one paper")
def paper_detail(
    request: Request,
    paper_id: int,
    session:   SessionDep,
):
    p = session.exec(select(PaperModel).where(PaperModel.id == paper_id)).first()
    if not p:
        raise HTTPException(404, f"Paper {paper_id} not found")

    mcqs = [ link.mcq for link in p.mcq_links ]
    # embed the full MCQs so your template can print them
    return templates.TemplateResponse("paper_detail.html", {
        "request":     request,
        "paper_id":    p.id,
        "created_at":  p.created_at,
        "mcqs":        mcqs,
        # you can still use pdf_url here if you generate one
        "pdf_url":     f"/papers/{p.id}/pdf",
    })



@router.get(
    "/papers/all",
    summary="HTML view of ALL papers (multi-paper)",
)
def all_papers_view(
    request: Request,
    session: SessionDep,
    show_answers: bool = Query(True, description="Show answers in the view?"),
    page: int       = Query(1, ge=1, description="Page number"),
    per_page: int   = Query(0, ge=0, le=100, description="Papers per page (0 = all)"),
):
    """
    Render every existing paper (or a slice, if paginated) into one long HTML page.
    Pass ?show_answers=false to hide answers.
    """
    # 1) count & pagination
    total = session.exec(select(func.count(PaperModel.id))).one()
    if per_page:
        total_pages = ceil(total / per_page)
        offset, limit = (page - 1) * per_page, per_page
    else:
        total_pages = 1
        offset, limit = 0, None

    # 2) fetch the requested slice
    stmt = select(PaperModel).order_by(desc(PaperModel.id)).offset(offset)
    if limit:
        stmt = stmt.limit(limit)
    papers = session.exec(stmt).all()
    if not papers:
        raise HTTPException(404, "No papers found")

    # 3) build contexts
    ctx = []
    for p in papers:
        mcqs = [link.mcq for link in p.mcq_links]
        ctx.append({
            "paper_id":   p.id,
            "created_at": p.created_at,
            "mcqs":       mcqs,
        })

    # 4) pick your template
    tpl = "all_papers_with_answers.html" if show_answers else "all_papers_q_only.html"

    return templates.TemplateResponse(
        tpl,
        {
            "request":      request,
            "papers":       ctx,
            "page":         page,
            "per_page":     per_page,
            "total":        total,
            "total_pages":  total_pages,
            "show_answers": show_answers,
        }
    )