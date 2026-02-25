"""
app/routes/community.py — MCQ community features.
Discussions (threaded), answer submissions, community stats, Urdu translations.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.database import get_session
from app.models.user import User
from app.models.community import (
    MCQDiscussion, MCQDiscussionCreate, MCQDiscussionRead,
    MCQSubmission, MCQSubmissionCreate, MCQStatsRead,
    MCQTranslation, MCQTranslationCreate, MCQTranslationRead,
)
from app.models.mcqs_bank import MCQ
from app.security import get_current_user, get_optional_user, require_admin
from app.routes.users import _log_activity
from app.models.learning import ActivityType

router = APIRouter(prefix="/mcqs", tags=["Community"])


# ─────────────────────────────────────────────────────────────
# Discussions
# ─────────────────────────────────────────────────────────────
@router.get("/{mcq_id}/discussions")
def list_discussions(
    mcq_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_session),
):
    offset = (page - 1) * limit
    # Top-level messages only (no parent)
    messages = db.exec(
        select(MCQDiscussion)
        .where(
            MCQDiscussion.mcq_id == mcq_id,
            MCQDiscussion.parent_id.is_(None),
            MCQDiscussion.is_deleted == False,
        )
        .order_by(MCQDiscussion.is_pinned.desc(), MCQDiscussion.created_at.desc())
        .offset(offset).limit(limit)
    ).all()
    total = db.exec(
        select(func.count(MCQDiscussion.id))
        .where(MCQDiscussion.mcq_id == mcq_id, MCQDiscussion.parent_id.is_(None), MCQDiscussion.is_deleted == False)
    ).one()

    result = []
    for msg in messages:
        replies = db.exec(
            select(MCQDiscussion)
            .where(MCQDiscussion.parent_id == msg.id, MCQDiscussion.is_deleted == False)
            .order_by(MCQDiscussion.created_at.asc())
        ).all()
        result.append({
            "id": msg.id,
            "author_name": msg.author_name,
            "author_city": msg.author_city,
            "body": msg.body,
            "upvotes": msg.upvotes,
            "is_pinned": msg.is_pinned,
            "created_at": msg.created_at,
            "replies": [
                {"id": r.id, "author_name": r.author_name, "author_city": r.author_city,
                 "body": r.body, "upvotes": r.upvotes, "created_at": r.created_at}
                for r in replies
            ],
        })
    return {"total": total, "page": page, "messages": result}


@router.post("/{mcq_id}/discussions", status_code=201)
def post_discussion(
    mcq_id: int,
    body: MCQDiscussionCreate,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_session),
):
    # Sanitize: strip HTML tags from body
    import re
    clean_body = re.sub(r"<[^>]+>", "", body.body).strip()
    if not clean_body:
        raise HTTPException(status_code=422, detail="Body cannot be empty")
    if len(clean_body) > 1500:
        raise HTTPException(status_code=422, detail="Body exceeds 1500 characters")

    msg = MCQDiscussion(
        mcq_id=mcq_id,
        user_id=current_user.id if current_user else None,
        author_name=body.author_name,
        author_email=body.author_email,  # stored privately, never returned
        author_city=body.author_city,
        body=clean_body,
        parent_id=body.parent_id,
    )
    db.add(msg)
    if current_user:
        _log_activity(db, current_user.id, ActivityType.discussion_post)
    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "body": msg.body, "author_name": msg.author_name, "created_at": msg.created_at}


@router.put("/{mcq_id}/discussions/{discussion_id}/upvote")
def upvote_discussion(
    mcq_id: int,
    discussion_id: str,
    db: Session = Depends(get_session),
):
    msg = db.get(MCQDiscussion, discussion_id)
    if not msg or msg.mcq_id != mcq_id or msg.is_deleted:
        raise HTTPException(status_code=404, detail="Discussion not found")
    msg.upvotes += 1
    db.add(msg)
    db.commit()
    return {"upvotes": msg.upvotes}


@router.delete("/discussions/{discussion_id}", status_code=204)
def delete_discussion(
    discussion_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    msg = db.get(MCQDiscussion, discussion_id)
    if not msg:
        raise HTTPException(status_code=404)
    msg.is_deleted = True
    db.add(msg)
    db.commit()


# ─────────────────────────────────────────────────────────────
# Submissions & Community Stats
# ─────────────────────────────────────────────────────────────
@router.post("/{mcq_id}/submit", status_code=201)
def submit_answer(
    mcq_id: int,
    body: MCQSubmissionCreate,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_session),
):
    mcq = db.get(MCQ, mcq_id)
    if not mcq:
        raise HTTPException(status_code=404, detail="MCQ not found")

    is_correct = mcq.correct_answer == body.selected_option

    sub = MCQSubmission(
        mcq_id=mcq_id,
        user_id=current_user.id if current_user else None,
        session_id=body.session_id,
        selected_option=body.selected_option,
        is_correct=is_correct,
        time_taken_seconds=body.time_taken_seconds,
    )
    db.add(sub)
    if current_user:
        _log_activity(db, current_user.id, ActivityType.mcq_attempt, points=2 if is_correct else 1)
    db.commit()

    return {
        "is_correct": is_correct,
        "correct_answer": mcq.correct_answer,
        "explanation": mcq.explanation if mcq.explanation not in (None, "[NO_EXPLANATION]") else None,
    }


@router.get("/{mcq_id}/stats", response_model=MCQStatsRead)
def mcq_stats(
    mcq_id: int,
    db: Session = Depends(get_session),
):
    subs = db.exec(select(MCQSubmission).where(MCQSubmission.mcq_id == mcq_id)).all()
    total = len(subs)
    if total == 0:
        return MCQStatsRead(
            mcq_id=mcq_id, total_attempts=0, correct_rate=0.0,
            distribution={}, recent_submitters=[],
        )

    correct_count = sum(1 for s in subs if s.is_correct)
    dist: dict[str, dict] = {}
    for opt in ["A", "B", "C", "D"]:
        count = sum(1 for s in subs if s.selected_option == opt)
        dist[opt] = {"count": count, "percent": round(count / total * 100, 1)}

    recent = db.exec(
        select(MCQSubmission)
        .where(MCQSubmission.mcq_id == mcq_id)
        .order_by(MCQSubmission.submitted_at.desc())
        .limit(5)
    ).all()

    return MCQStatsRead(
        mcq_id=mcq_id,
        total_attempts=total,
        correct_rate=round(correct_count / total, 2),
        distribution=dist,
        recent_submitters=[
            {"selected": s.selected_option, "is_correct": s.is_correct}
            for s in recent
        ],
    )


# ─────────────────────────────────────────────────────────────
# Translations
# ─────────────────────────────────────────────────────────────
@router.get("/{mcq_id}/translation", response_model=MCQTranslationRead)
def get_translation(
    mcq_id: int,
    locale: str = Query("ur"),
    db: Session = Depends(get_session),
):
    tr = db.exec(
        select(MCQTranslation)
        .where(MCQTranslation.mcq_id == mcq_id, MCQTranslation.locale == locale)
    ).one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail=f"No {locale} translation for this MCQ")
    return tr


@router.post("/{mcq_id}/translation", status_code=201, response_model=MCQTranslationRead)
def create_translation(
    mcq_id: int,
    body: MCQTranslationCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    existing = db.exec(
        select(MCQTranslation)
        .where(MCQTranslation.mcq_id == mcq_id, MCQTranslation.locale == body.locale)
    ).one_or_none()
    if existing:
        # Update
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(existing, k, v)
        existing.updated_at = datetime.now(timezone.utc)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    tr = MCQTranslation(mcq_id=mcq_id, **body.model_dump())
    db.add(tr)
    db.commit()
    db.refresh(tr)
    return tr
