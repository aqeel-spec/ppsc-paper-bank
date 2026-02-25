"""
app/routes/daily_papers.py — One daily test paper per day.
Admins assign papers to dates; users get today's paper and attempt it.
"""
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models.user import User
from app.models.session import DailyPaper, DailyPaperAttempt, DailyPaperAttemptRead, DailyPaperRead
from app.models.paper import PaperModel
from app.security import get_current_user, require_admin
from app.routes.users import _log_activity
from app.models.learning import ActivityType

router = APIRouter(prefix="/daily-papers", tags=["Daily Papers"])


# ---------------------------------------------------------------------------
# Get today's paper
# ---------------------------------------------------------------------------
@router.get("/today")
def today_paper(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    today = date.today()
    dp = db.exec(
        select(DailyPaper).where(DailyPaper.paper_date == today, DailyPaper.is_active == True)
    ).one_or_none()
    if not dp:
        raise HTTPException(status_code=404, detail="No daily paper available today")

    # Check if user already attempted today
    attempt = db.exec(
        select(DailyPaperAttempt)
        .where(DailyPaperAttempt.user_id == current_user.id, DailyPaperAttempt.daily_paper_id == dp.id)
    ).one_or_none()

    paper = db.get(PaperModel, dp.paper_id)
    return {
        "daily_paper": dp,
        "paper": {"id": paper.id, "title": paper.title} if paper else None,
        "already_attempted": attempt is not None,
        "attempt": attempt,
    }


# ---------------------------------------------------------------------------
# Start today's paper attempt
# ---------------------------------------------------------------------------
@router.post("/today/start", status_code=201)
def start_today_paper(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    today = date.today()
    dp = db.exec(
        select(DailyPaper).where(DailyPaper.paper_date == today, DailyPaper.is_active == True)
    ).one_or_none()
    if not dp:
        raise HTTPException(status_code=404, detail="No daily paper today")

    existing = db.exec(
        select(DailyPaperAttempt)
        .where(DailyPaperAttempt.user_id == current_user.id, DailyPaperAttempt.daily_paper_id == dp.id)
    ).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Already attempted today's paper")

    attempt = DailyPaperAttempt(user_id=current_user.id, daily_paper_id=dp.id)
    db.add(attempt)
    _log_activity(db, current_user.id, ActivityType.daily_paper)
    db.commit()
    db.refresh(attempt)
    return attempt


# ---------------------------------------------------------------------------
# Get paper by date
# ---------------------------------------------------------------------------
@router.get("/{paper_date}", response_model=DailyPaperRead)
def get_paper_by_date(
    paper_date: date,
    db: Session = Depends(get_session),
):
    dp = db.exec(select(DailyPaper).where(DailyPaper.paper_date == paper_date)).one_or_none()
    if not dp:
        raise HTTPException(status_code=404, detail="No paper for this date")
    return dp


# ---------------------------------------------------------------------------
# User's attempt history
# ---------------------------------------------------------------------------
@router.get("/history/me", response_model=list[DailyPaperAttemptRead])
def attempt_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
):
    return db.exec(
        select(DailyPaperAttempt)
        .where(DailyPaperAttempt.user_id == current_user.id)
        .order_by(DailyPaperAttempt.created_at.desc())
        .offset(offset).limit(limit)
    ).all()


# ---------------------------------------------------------------------------
# Admin: assign a paper to a date
# ---------------------------------------------------------------------------
@router.post("/admin/assign", status_code=201, response_model=DailyPaperRead)
def assign_daily_paper(
    paper_id: int,
    paper_date: date,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    paper = db.get(PaperModel, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    existing = db.exec(select(DailyPaper).where(DailyPaper.paper_date == paper_date)).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A paper is already assigned for this date")

    dp = DailyPaper(paper_date=paper_date, paper_id=paper_id, created_by=admin.id)
    db.add(dp)
    db.commit()
    db.refresh(dp)
    return dp
