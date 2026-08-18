from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.database import get_session
from app.models.user import User
from app.models.vocab import DayPlan, Word, WordCreate, WordRead
from app.security import get_current_user
from app.services.email_service import broadcast_email_message

router = APIRouter(prefix="/api", tags=["Vocabulary"])

INTERVAL_DAYS = {1: 0, 2: 3, 3: 7, 4: 14, 5: 30}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_cron_secret(request: Request) -> None:
    expected = os.getenv("CRON_SECRET", "").strip()
    header = request.headers.get("Authorization", "")
    if not expected:
        raise HTTPException(status_code=500, detail="CRON_SECRET is not configured")
    if header != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")


def _day_from_query(value: Optional[str]) -> Optional[date]:
    if value in (None, ""):
        return None
    return date.fromisoformat(value)


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


@router.get("/words", response_model=list[WordRead])
def list_words(
    date_value: Optional[str] = Query(default=None, alias="date"),
    due: bool = Query(default=False),
    q: Optional[str] = Query(default=None, description="Search by word, meaning, synonyms, antonyms, sentence, hook, tags"),
    tag: Optional[str] = Query(default=None, description="Filter words by tag"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    target_date = _day_from_query(date_value)
    query = select(Word).where(Word.user_id == current_user.id)

    if due:
        query = query.where(Word.next_review <= _utc_now())
    elif target_date is not None:
        query = query.where(Word.scheduled_date == target_date)

    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(
            or_(
                Word.word.ilike(term),
                Word.meaning.ilike(term),
                Word.relevant_meaning.ilike(term),
                Word.sentence.ilike(term),
                Word.hook.ilike(term),
                Word.synonyms.ilike(term),
                Word.antonyms.ilike(term),
                Word.tags.ilike(term),
            )
        )

    if tag and tag.strip():
        tag_term = f"%{tag.strip()}%"
        query = query.where(Word.tags.ilike(tag_term))

    query = query.order_by(Word.next_review.asc(), Word.created_at.asc())
    return db.exec(query).all()


@router.post("/words", response_model=WordRead, status_code=201)
def create_word(
    payload: WordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    if not payload.word.strip():
        raise HTTPException(status_code=400, detail="word is required")
    if not payload.meaning.strip():
        raise HTTPException(status_code=400, detail="meaning is required")

    day_plan = db.exec(
        select(DayPlan).where(
            DayPlan.user_id == current_user.id,
            DayPlan.plan_date == payload.scheduled_date,
        )
    ).one_or_none()
    if day_plan is None:
        day_plan = DayPlan(user_id=current_user.id, plan_date=payload.scheduled_date, target_count=5)
        db.add(day_plan)

    record = Word(
        user_id=current_user.id,
        word=payload.word.strip(),
        meaning=payload.meaning.strip(),
        relevant_meaning=_clean_optional_text(payload.relevant_meaning),
        sentence=_clean_optional_text(payload.sentence),
        hook=_clean_optional_text(payload.hook),
        synonyms=_clean_optional_text(payload.synonyms),
        antonyms=_clean_optional_text(payload.antonyms),
        tags=_clean_optional_text(payload.tags),
        scheduled_date=payload.scheduled_date,
        next_review=_utc_now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/words/{word_id}")
def update_word(
    word_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    word = db.get(Word, word_id)
    if word is None or word.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Word not found")

    action = (payload.get("action") or "").strip().lower()

    if action == "complete":
        word.completed = not word.completed
        db.add(word)
        db.commit()
        return {"id": word.id, "completed": word.completed}

    if action == "grade":
        correct = bool(payload.get("correct", False))
        if correct:
            word.box = min(5, word.box + 1)
        else:
            word.box = 1
        word.next_review = _utc_now() + timedelta(days=INTERVAL_DAYS.get(word.box, 0))
        word.revision_reminder_sent_at = None
        word.completed = False
        db.add(word)
        db.commit()
        return {"id": word.id, "box": word.box, "next_review": word.next_review.isoformat()}

    raise HTTPException(status_code=400, detail="Unsupported action")


@router.get("/plan")
def get_plan(
    month: str = Query(..., description="YYYY-MM"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    try:
        year, month_number = map(int, month.split("-", 1))
        if month_number < 1 or month_number > 12:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format") from exc

    month_start = date(year, month_number, 1)
    if month_number == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month_number + 1, 1)

    rows = db.exec(
        select(Word.scheduled_date, func.count(Word.id))
        .where(
            Word.user_id == current_user.id,
            Word.scheduled_date >= month_start,
            Word.scheduled_date < next_month,
        )
        .group_by(Word.scheduled_date)
    ).all()

    return [{"date": item[0].isoformat(), "count": int(item[1])} for item in rows]


@router.get("/cron/reminders")
def cron_reminders(request: Request, db: Session = Depends(get_session)):
    _require_cron_secret(request)
    now = _utc_now()
    today = now.date()
    cutoff_hour = int(os.getenv("DAY_CUTOFF_HOUR", "22"))
    cutoff_time = datetime.combine(today, time(cutoff_hour, 0), tzinfo=timezone.utc)
    reminder_start = cutoff_time - timedelta(hours=4)
    today_plan = db.exec(select(DayPlan).where(DayPlan.plan_date == today)).one_or_none()
    word_count_today = db.exec(select(func.count(Word.id)).where(Word.scheduled_date == today)).one()
    target_count = (today_plan.target_count if today_plan else 5)

    today_reminder_sent = False
    if reminder_start <= now <= cutoff_time and word_count_today < target_count and (today_plan is None or today_plan.due_reminder_sent_at is None):
        recipients = [item.strip() for item in (os.getenv("REMINDER_TO_EMAIL", "").strip() or "").split(",") if item.strip()]
        if recipients:
            subject = "You haven't added today's 5 words yet"
            body = f"You currently have {word_count_today}/{target_count} words planned for {today.isoformat()}. Add the remaining words before the daily cutoff."
            broadcast_email_message(subject, body, recipients)
        if today_plan is None:
            today_plan = DayPlan(plan_date=today, target_count=target_count)
            db.add(today_plan)
        today_plan.due_reminder_sent_at = now
        db.add(today_plan)
        today_reminder_sent = True

    due_window_start = now + timedelta(hours=11)
    due_window_end = now + timedelta(hours=13)
    due_words = db.exec(
        select(Word)
        .where(
            Word.next_review >= due_window_start,
            Word.next_review <= due_window_end,
            Word.revision_reminder_sent_at.is_(None),
        )
    ).all()

    revision_reminder_count = 0
    if due_words:
        recipients = [item.strip() for item in (os.getenv("REMINDER_TO_EMAIL", "").strip() or "").split(",") if item.strip()]
        if recipients:
            names = ", ".join(word.word for word in due_words)
            subject = f"{len(due_words)} word(s) due for revision in ~12 hours"
            body = f"Words due soon: {names}"
            broadcast_email_message(subject, body, recipients)
        for word in due_words:
            word.revision_reminder_sent_at = now
            db.add(word)
            revision_reminder_count += 1

    db.commit()
    return {
        "todayReminderSent": today_reminder_sent,
        "revisionReminderCount": revision_reminder_count,
        "generatedAt": now.isoformat(),
    }
