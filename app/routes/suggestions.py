"""
app/routes/suggestions.py — User site improvement suggestions.
Anyone can submit. Logged-in users can upvote. Admin manages status.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.database import get_session
from app.models.user import User
from app.models.suggestion import (
    UserSuggestion, SuggestionCreate, SuggestionRead, SuggestionAdminUpdate,
    SuggestionUpvote, SuggestionStatus,
)
from app.security import get_current_user, get_optional_user, require_admin

router = APIRouter(prefix="/suggestions", tags=["Suggestions"])


# ---------------------------------------------------------------------------
# Public: list accepted suggestions
# ---------------------------------------------------------------------------
@router.get("", response_model=list[SuggestionRead])
def list_suggestions(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_session),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
):
    q = select(UserSuggestion).where(
        UserSuggestion.status.in_([SuggestionStatus.accepted, SuggestionStatus.reviewed])
    )
    if category:
        q = q.where(UserSuggestion.category == category)
    q = q.order_by(UserSuggestion.upvotes.desc(), UserSuggestion.created_at.desc()).offset(offset).limit(limit)
    return db.exec(q).all()


# ---------------------------------------------------------------------------
# Submit suggestion (auth optional — anonymous allowed)
# ---------------------------------------------------------------------------
@router.post("", status_code=201, response_model=SuggestionRead)
def submit_suggestion(
    body: SuggestionCreate,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_session),
):
    suggestion = UserSuggestion(
        user_id=current_user.id if current_user else None,
        **body.model_dump(),
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion


# ---------------------------------------------------------------------------
# Upvote a suggestion (auth required to prevent duplicate votes)
# ---------------------------------------------------------------------------
@router.put("/{suggestion_id}/upvote")
def upvote_suggestion(
    suggestion_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    s = db.get(UserSuggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    # Prevent double upvote
    existing = db.exec(
        select(SuggestionUpvote).where(
            SuggestionUpvote.suggestion_id == suggestion_id,
            SuggestionUpvote.user_id == current_user.id,
        )
    ).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Already upvoted")

    upvote = SuggestionUpvote(suggestion_id=suggestion_id, user_id=current_user.id)
    db.add(upvote)
    s.upvotes += 1
    db.add(s)
    db.commit()
    return {"upvotes": s.upvotes}


# ---------------------------------------------------------------------------
# My suggestions
# ---------------------------------------------------------------------------
@router.get("/my", response_model=list[SuggestionRead])
def my_suggestions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    return db.exec(
        select(UserSuggestion)
        .where(UserSuggestion.user_id == current_user.id)
        .order_by(UserSuggestion.created_at.desc())
    ).all()


# ---------------------------------------------------------------------------
# Admin: list all suggestions
# ---------------------------------------------------------------------------
@router.get("/admin/all", response_model=list[SuggestionRead])
def admin_list_suggestions(
    status: Optional[str] = Query(None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    q = select(UserSuggestion)
    if status:
        q = q.where(UserSuggestion.status == status)
    q = q.order_by(UserSuggestion.created_at.desc()).offset(offset).limit(limit)
    return db.exec(q).all()


# ---------------------------------------------------------------------------
# Admin: update status / reply
# ---------------------------------------------------------------------------
@router.patch("/admin/{suggestion_id}", response_model=SuggestionRead)
def admin_update_suggestion(
    suggestion_id: str,
    body: SuggestionAdminUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    s = db.get(UserSuggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    s.updated_at = datetime.now(timezone.utc)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ---------------------------------------------------------------------------
# Admin: delete a suggestion
# ---------------------------------------------------------------------------
@router.delete("/admin/{suggestion_id}", status_code=204)
def admin_delete_suggestion(
    suggestion_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    s = db.get(UserSuggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404)
    db.delete(s)
    db.commit()
