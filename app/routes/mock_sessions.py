"""
app/routes/mock_sessions.py — Mock exam session lifecycle.
Credit-gated: each session costs 1 credit (admins are unlimited).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.database import get_session
from app.models.user import User, UserRole
from app.models.session import (
    MockSession, MockSessionCreate, MockSessionRead,
    MockSessionAnswer, MockSessionAnswerCreate, MockSessionStatus,
)
from app.models.mcqs_bank import MCQ
from app.models.paper import PaperModel, PaperMCQ
from app.security import get_current_user
from app.routes.users import _log_activity
from app.models.learning import ActivityType

router = APIRouter(prefix="/mock-sessions", tags=["Mock Sessions"])


# ---------------------------------------------------------------------------
# List user's sessions
# ---------------------------------------------------------------------------
@router.get("", response_model=list[MockSessionRead])
def list_sessions(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
):
    return session.exec(
        select(MockSession)
        .where(MockSession.user_id == current_user.id)
        .order_by(MockSession.created_at.desc())
        .offset(offset).limit(limit)
    ).all()


# ---------------------------------------------------------------------------
# Create / start a session (credit gate)
# ---------------------------------------------------------------------------
@router.post("", response_model=MockSessionRead, status_code=201)
def create_session(
    body: MockSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    is_admin = current_user.role == UserRole.admin

    if not is_admin and current_user.credits < 1:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits. Please purchase more credits to start a mock session.",
        )

    # Validate paper exists if supplied
    if body.paper_id:
        paper = db.get(PaperModel, body.paper_id)
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        mcq_count = len(paper.mcqs) if hasattr(paper, "mcqs") else 0
    else:
        mcq_count = 0

    # Deduct credit (not for admins)
    credit_used = False
    if not is_admin:
        current_user.credits -= 1
        credit_used = True
        db.add(current_user)

    mock = MockSession(
        user_id=current_user.id,
        paper_id=body.paper_id,
        status=MockSessionStatus.started,
        total_questions=mcq_count,
        credit_used=credit_used,
        started_at=datetime.now(timezone.utc),
    )
    db.add(mock)
    _log_activity(db, current_user.id, ActivityType.mock_session)
    db.commit()
    db.refresh(mock)
    return mock


# ---------------------------------------------------------------------------
# Get session with MCQs
# ---------------------------------------------------------------------------
@router.get("/{session_id}")
def get_session_detail(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    mock = db.exec(
        select(MockSession).where(MockSession.id == session_id, MockSession.user_id == current_user.id)
    ).one_or_none()
    if not mock:
        raise HTTPException(status_code=404, detail="Session not found")

    mcqs = []
    if mock.paper_id:
        paper_mcqs = db.exec(select(PaperMCQ).where(PaperMCQ.paper_id == mock.paper_id)).all()
        mcq_ids = [pm.mcq_id for pm in paper_mcqs]
        mcqs = db.exec(select(MCQ).where(MCQ.id.in_(mcq_ids))).all()

    return {
        "session": mock,
        "mcqs": [
            {"id": m.id, "question_text": m.question_text, "options": m.options, "correct_answer": m.correct_answer}
            for m in mcqs
        ],
    }


# ---------------------------------------------------------------------------
# Submit an answer
# ---------------------------------------------------------------------------
@router.post("/{session_id}/answer", status_code=201)
def submit_answer(
    session_id: str,
    body: MockSessionAnswerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    mock = db.exec(
        select(MockSession).where(MockSession.id == session_id, MockSession.user_id == current_user.id)
    ).one_or_none()
    if not mock or mock.status != MockSessionStatus.started:
        raise HTTPException(status_code=404, detail="Active session not found")

    mcq = db.get(MCQ, body.mcq_id)
    if not mcq:
        raise HTTPException(status_code=404, detail="MCQ not found")

    is_correct = mcq.correct_answer == body.selected_option

    answer = MockSessionAnswer(
        session_id=session_id,
        mcq_id=body.mcq_id,
        selected_option=body.selected_option,
        is_correct=is_correct,
        time_taken_seconds=body.time_taken_seconds,
    )
    db.add(answer)
    db.commit()
    return {"is_correct": is_correct, "correct_answer": mcq.correct_answer}


# ---------------------------------------------------------------------------
# Finish session
# ---------------------------------------------------------------------------
@router.post("/{session_id}/finish")
def finish_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    mock = db.exec(
        select(MockSession).where(MockSession.id == session_id, MockSession.user_id == current_user.id)
    ).one_or_none()
    if not mock:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = db.exec(select(MockSessionAnswer).where(MockSessionAnswer.session_id == session_id)).all()
    correct = sum(1 for a in answers if a.is_correct)
    total = len(answers)
    score = round((correct / total) * 100, 2) if total > 0 else 0

    mock.status = MockSessionStatus.completed
    mock.correct_answers = correct
    mock.total_questions = total
    mock.score = score
    mock.completed_at = datetime.now(timezone.utc)
    db.add(mock)
    db.commit()
    return {"score": score, "correct": correct, "total": total}


# ---------------------------------------------------------------------------
# Session results
# ---------------------------------------------------------------------------
@router.get("/{session_id}/results")
def session_results(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    mock = db.exec(
        select(MockSession).where(MockSession.id == session_id, MockSession.user_id == current_user.id)
    ).one_or_none()
    if not mock:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = db.exec(select(MockSessionAnswer).where(MockSessionAnswer.session_id == session_id)).all()
    per_mcq = []
    for ans in answers:
        mcq = db.get(MCQ, ans.mcq_id)
        per_mcq.append({
            "mcq_id": ans.mcq_id,
            "question": mcq.question_text if mcq else None,
            "selected": ans.selected_option,
            "correct_answer": mcq.correct_answer if mcq else None,
            "is_correct": ans.is_correct,
            "time_taken": ans.time_taken_seconds,
        })

    return {
        "session_id": session_id,
        "score": mock.score,
        "correct": mock.correct_answers,
        "total": mock.total_questions,
        "per_mcq": per_mcq,
    }
