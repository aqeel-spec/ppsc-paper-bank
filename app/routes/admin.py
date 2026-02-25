"""
app/routes/admin.py — Admin-only management panel.
User management, credit adjustment, platform stats, moderation.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.database import get_session
from app.models.user import User, UserRead, UserRole
from app.models.community import MCQDiscussion, MCQSubmission
from app.models.session import MockSession, DailyPaper
from app.models.learning import LearningActivity
from app.models.suggestion import UserSuggestion
from app.security import require_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@router.get("/users", response_model=list[UserRead])
def list_users(
    role: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    q = select(User)
    if role:
        q = q.where(User.role == role)
    return db.exec(q.offset(offset).limit(limit)).all()


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/users/{user_id}/credits")
def adjust_credits(
    user_id: str,
    amount: int = Query(..., description="Positive to add, negative to deduct"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.credits = max(0, user.credits + amount)
    db.add(user)
    db.commit()
    return {"user_id": user_id, "new_credits": user.credits}


@router.patch("/users/{user_id}/role")
def change_role(
    user_id: str,
    role: UserRole = Query(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = role
    db.add(user)
    db.commit()
    return {"user_id": user_id, "role": user.role}


@router.patch("/users/{user_id}/active")
def toggle_active(
    user_id: str,
    is_active: bool = Query(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = is_active
    db.add(user)
    db.commit()
    return {"user_id": user_id, "is_active": user.is_active}


# ---------------------------------------------------------------------------
# Platform Statistics
# ---------------------------------------------------------------------------
@router.get("/stats")
def platform_stats(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    total_users = db.exec(select(func.count(User.id))).one()
    total_submissions = db.exec(select(func.count(MCQSubmission.id))).one()
    total_mock_sessions = db.exec(select(func.count(MockSession.id))).one()
    total_discussions = db.exec(
        select(func.count(MCQDiscussion.id)).where(MCQDiscussion.is_deleted == False)
    ).one()
    pending_suggestions = db.exec(
        select(func.count(UserSuggestion.id)).where(UserSuggestion.status == "pending")
    ).one()
    return {
        "total_users": total_users,
        "total_submissions": total_submissions,
        "total_mock_sessions": total_mock_sessions,
        "total_discussions": total_discussions,
        "pending_suggestions": pending_suggestions,
    }


# ---------------------------------------------------------------------------
# Discussion Moderation queue
# ---------------------------------------------------------------------------
@router.get("/discussions/flagged")
def flagged_discussions(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
    limit: int = Query(50),
):
    return db.exec(
        select(MCQDiscussion)
        .where(MCQDiscussion.is_flagged == True, MCQDiscussion.is_deleted == False)
        .order_by(MCQDiscussion.created_at.desc())
        .limit(limit)
    ).all()


@router.patch("/discussions/{discussion_id}/pin")
def pin_discussion(
    discussion_id: str,
    is_pinned: bool = Query(True),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    msg = db.get(MCQDiscussion, discussion_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Discussion not found")
    msg.is_pinned = is_pinned
    db.add(msg)
    db.commit()
    return {"id": discussion_id, "is_pinned": is_pinned}


# ---------------------------------------------------------------------------
# Daily Paper management (also available in daily_papers.py but duplicated here for admin UI)
# ---------------------------------------------------------------------------
@router.get("/daily-papers")
def list_daily_papers(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
    limit: int = Query(30, le=365),
):
    return db.exec(
        select(DailyPaper).order_by(DailyPaper.paper_date.desc()).limit(limit)
    ).all()
