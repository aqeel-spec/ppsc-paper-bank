from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlmodel import SQLModel, Session, select

from app.database import get_engine, get_session
from app.models.user import User
from app.models.vocab import (
    BOX_INTERVAL_DAYS,
    BOX_LEVEL_LABELS,
    BUILTIN_CARD_THEMES,
    VOCAB_METHODS,
    DayPlan,
    UserVocabSettings,
    UserVocabSettingsRead,
    UserVocabSettingsUpdate,
    VocabCustomTheme,
    VocabCustomThemeCreate,
    VocabCustomThemeRead,
    VocabDailyProgress,
    VocabDailyProgressRead,
    VocabDailyProgressSync,
    VocabAiExplanation,
    VocabAiExplanationCreate,
    VocabAiExplanationRead,
    VocabQuizResult,
    VocabQuizResultCreate,
    VocabQuizResultRead,
    Word,
    WordCreate,
    WordRead,
)
from app.security import get_current_user
from app.services.email_service import broadcast_email_message
from agents import Agent, Runner, SQLiteSession
from ppsc_agents.agent_system import SESSION_DB, get_current_model

router = APIRouter(prefix="/api", tags=["Vocabulary"])

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


def _clamp_cards_per_day(value: Optional[int]) -> int:
    if value is None:
        return 5
    return max(1, min(50, int(value)))


def _method_keys() -> set[str]:
    return {item["key"] for item in VOCAB_METHODS}


def _builtin_theme_keys() -> set[str]:
    return {item["key"] for item in BUILTIN_CARD_THEMES}


def _today_progress_for_user(db: Session, user_id: str) -> VocabDailyProgress:
    today = _utc_now().date()
    record = db.exec(
        select(VocabDailyProgress).where(
            VocabDailyProgress.user_id == user_id,
            VocabDailyProgress.progress_date == today,
        )
    ).one_or_none()
    if record is None:
        record = VocabDailyProgress(user_id=user_id, progress_date=today)
        db.add(record)
    return record


def _compute_progress_metrics(progress: VocabDailyProgress) -> None:
    if progress.reviews_done > 0:
        progress.retention_rate = round((progress.correct_reviews / progress.reviews_done) * 100.0, 2)
    else:
        progress.retention_rate = None

    pace_base = progress.words_added + progress.reviews_done
    if pace_base > 0:
        progress.pace_score = round(pace_base / 5.0, 2)
    else:
        progress.pace_score = None


def _trigger_vocab_reminder_job(triggered_at_iso: str) -> None:
    engine = get_engine()
    with Session(engine) as db:
        try:
            parsed = datetime.fromisoformat(triggered_at_iso)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            now = parsed.astimezone(timezone.utc)
        except ValueError:
            now = _utc_now()
        _run_vocab_reminder_job(db, now)


def _run_vocab_reminder_job(db: Session, now: datetime) -> dict:
    today = now.date()
    cutoff_hour = int(os.getenv("DAY_CUTOFF_HOUR", "22"))
    cutoff_time = datetime.combine(today, time(cutoff_hour, 0), tzinfo=timezone.utc)
    reminder_start = cutoff_time - timedelta(hours=4)
    in_today_window = reminder_start <= now <= cutoff_time

    due_window_start = now + timedelta(hours=11)
    due_window_end = now + timedelta(hours=13)

    users = db.exec(select(User).where(User.is_active == True)).all()
    today_reminder_sent = 0
    revision_reminder_count = 0

    for user in users:
        if not user.email or not user.email.strip():
            continue
        recipient = user.email.strip()

        settings = db.get(UserVocabSettings, user.id)
        target_count = settings.cards_per_day if settings else 5

        today_progress = db.exec(
            select(VocabDailyProgress).where(
                VocabDailyProgress.user_id == user.id,
                VocabDailyProgress.progress_date == today,
            )
        ).one_or_none()
        if today_progress is None:
            today_progress = VocabDailyProgress(user_id=user.id, progress_date=today)
            db.add(today_progress)

        word_count_today = db.exec(
            select(func.count(Word.id)).where(
                Word.user_id == user.id,
                Word.scheduled_date == today,
            )
        ).one()

        if in_today_window and word_count_today < target_count and today_progress.due_reminder_sent_at is None:
            subject = "You haven't added today's vocab update yet"
            body = (
                f"You currently have {word_count_today}/{target_count} words for {today.isoformat()}. "
                "Please add your remaining words before the daily cutoff."
            )
            broadcast_email_message(subject, body, [recipient])
            today_progress.due_reminder_sent_at = now
            today_progress.updated_at = now
            db.add(today_progress)
            today_reminder_sent += 1

        due_words = db.exec(
            select(Word)
            .where(
                Word.user_id == user.id,
                Word.next_review >= due_window_start,
                Word.next_review <= due_window_end,
                Word.revision_reminder_sent_at.is_(None),
            )
            .order_by(Word.next_review.asc())
        ).all()

        if due_words:
            names = ", ".join(word.word for word in due_words)
            subject = f"{len(due_words)} vocab card(s) due for revision in ~12 hours"
            body = f"Words due soon: {names}"
            broadcast_email_message(subject, body, [recipient])

            for due_word in due_words:
                due_word.revision_reminder_sent_at = now
                db.add(due_word)
                revision_reminder_count += 1

    db.commit()
    return {
        "todayReminderSent": today_reminder_sent,
        "revisionReminderCount": revision_reminder_count,
        "processedUsers": len(users),
        "generatedAt": now.isoformat(),
    }


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

    progress = _today_progress_for_user(db, current_user.id)
    progress.words_added += 1
    _compute_progress_metrics(progress)
    progress.updated_at = _utc_now()
    db.add(progress)

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
        recall_seconds = payload.get("recallSeconds")
        if correct:
            word.box = min(5, word.box + 1)
        else:
            word.box = 1
        word.next_review = _utc_now() + timedelta(days=BOX_INTERVAL_DAYS.get(word.box, 1))
        word.revision_reminder_sent_at = None
        word.completed = False
        db.add(word)

        progress = _today_progress_for_user(db, current_user.id)
        progress.reviews_done += 1
        if correct:
            progress.correct_reviews += 1
        else:
            progress.wrong_reviews += 1

        if isinstance(recall_seconds, int) and recall_seconds > 0:
            if progress.avg_recall_seconds is None:
                progress.avg_recall_seconds = recall_seconds
            else:
                progress.avg_recall_seconds = int((progress.avg_recall_seconds + recall_seconds) / 2)

        _compute_progress_metrics(progress)
        progress.updated_at = _utc_now()
        db.add(progress)

        db.commit()
        return {"id": word.id, "box": word.box, "next_review": word.next_review.isoformat()}

    raise HTTPException(status_code=400, detail="Unsupported action")




@router.put("/words/{word_id}", response_model=WordRead)
def put_update_word(
    word_id: str,
    payload: WordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Full update (PUT) of a vocabulary card."""
    word = db.get(Word, word_id)
    if word is None or word.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Word not found")

    word.word = payload.word.strip()
    word.meaning = payload.meaning.strip()
    word.relevant_meaning = _clean_optional_text(payload.relevant_meaning)
    word.sentence = _clean_optional_text(payload.sentence)
    word.hook = _clean_optional_text(payload.hook)
    word.synonyms = _clean_optional_text(payload.synonyms)
    word.antonyms = _clean_optional_text(payload.antonyms)
    word.tags = _clean_optional_text(payload.tags)
    if payload.scheduled_date:
        word.scheduled_date = payload.scheduled_date

    db.add(word)
    db.commit()
    db.refresh(word)
    return word


@router.delete("/words/{word_id}", status_code=200)
def delete_word(
    word_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Delete a vocabulary card owned by the current user."""
    word = db.get(Word, word_id)
    if word is None or word.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Word not found")

    db.delete(word)
    db.commit()
    return {"success": True, "id": word_id}


@router.get("/words/box-intervals")
def get_box_intervals():
    return [
        {
            "box": box,
            "intervalDays": BOX_INTERVAL_DAYS[box],
            "label": BOX_LEVEL_LABELS[box],
        }
        for box in sorted(BOX_INTERVAL_DAYS.keys())
    ]


@router.get("/words/methods")
def get_vocab_methods():
    return VOCAB_METHODS


@router.get("/words/themes")
def get_vocab_themes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    custom = db.exec(
        select(VocabCustomTheme)
        .where(VocabCustomTheme.user_id == current_user.id)
        .order_by(VocabCustomTheme.created_at.desc())
    ).all()
    return {
        "builtin": BUILTIN_CARD_THEMES,
        "custom": custom,
    }


@router.post("/words/themes/custom", response_model=VocabCustomThemeRead, status_code=201)
def create_custom_theme(
    payload: VocabCustomThemeCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Theme name is required")

    record = VocabCustomTheme(
        user_id=current_user.id,
        name=name,
        theme_config=_clean_optional_text(payload.theme_config),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/words/settings", response_model=UserVocabSettingsRead)
def get_vocab_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    settings = db.get(UserVocabSettings, current_user.id)
    if settings is None:
        settings = UserVocabSettings(user_id=current_user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.patch("/words/settings", response_model=UserVocabSettingsRead)
def update_vocab_settings(
    payload: UserVocabSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    settings = db.get(UserVocabSettings, current_user.id)
    if settings is None:
        settings = UserVocabSettings(user_id=current_user.id)
        db.add(settings)

    updates = payload.model_dump(exclude_unset=True)

    if "cards_per_day" in updates:
        settings.cards_per_day = _clamp_cards_per_day(updates["cards_per_day"])

    if "selected_method" in updates and updates["selected_method"] is not None:
        selected_method = updates["selected_method"].strip()
        if selected_method not in _method_keys():
            raise HTTPException(status_code=400, detail="Unknown vocabulary method")
        settings.selected_method = selected_method

    if "selected_theme" in updates and updates["selected_theme"] is not None:
        selected_theme = updates["selected_theme"].strip()
        if selected_theme not in _builtin_theme_keys():
            custom_exists = db.exec(
                select(VocabCustomTheme).where(
                    VocabCustomTheme.user_id == current_user.id,
                    VocabCustomTheme.id == selected_theme,
                )
            ).one_or_none()
            if custom_exists is None:
                raise HTTPException(status_code=400, detail="Unknown theme")
        settings.selected_theme = selected_theme

    if "custom_card_fields" in updates:
        settings.custom_card_fields = _clean_optional_text(updates["custom_card_fields"])

    if "notes" in updates:
        settings.notes = _clean_optional_text(updates["notes"])

    settings.updated_at = _utc_now()
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


@router.post("/words/progress/sync", response_model=VocabDailyProgressRead)
def sync_progress(
    payload: VocabDailyProgressSync,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    target_date = payload.progress_date or _utc_now().date()
    record = db.exec(
        select(VocabDailyProgress).where(
            VocabDailyProgress.user_id == current_user.id,
            VocabDailyProgress.progress_date == target_date,
        )
    ).one_or_none()
    if record is None:
        record = VocabDailyProgress(user_id=current_user.id, progress_date=target_date)

    record.words_added = max(0, payload.words_added)
    record.reviews_done = max(0, payload.reviews_done)
    record.correct_reviews = max(0, payload.correct_reviews)
    record.wrong_reviews = max(0, payload.wrong_reviews)
    if payload.avg_recall_seconds is not None and payload.avg_recall_seconds > 0:
        record.avg_recall_seconds = payload.avg_recall_seconds

    _compute_progress_metrics(record)
    record.updated_at = _utc_now()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/words/progress", response_model=list[VocabDailyProgressRead])
def get_progress(
    days: int = Query(default=14, ge=1, le=120),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    start_day = _utc_now().date() - timedelta(days=days - 1)
    rows = db.exec(
        select(VocabDailyProgress)
        .where(
            VocabDailyProgress.user_id == current_user.id,
            VocabDailyProgress.progress_date >= start_day,
        )
        .order_by(VocabDailyProgress.progress_date.asc())
    ).all()
    return rows


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
def cron_reminders(request: Request, background_tasks: BackgroundTasks):
    _require_cron_secret(request)
    queued_at = _utc_now().isoformat()
    background_tasks.add_task(_trigger_vocab_reminder_job, queued_at)
    return {
        "queued": True,
        "queuedAt": queued_at,
        "message": "Vocab reminder job scheduled in background",
    }


# ─── AI Vocabulary Explanations Endpoints ─────────────────────────────────────

@router.post("/vocab/ai-explanations", response_model=VocabAiExplanationRead, status_code=201)
@router.post("/words/ai-explanations", response_model=VocabAiExplanationRead, status_code=201)
def save_ai_explanation(
    payload: VocabAiExplanationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Save an AI explanation generation for a vocabulary card/word."""
    word_text = payload.word.strip()
    if not word_text:
        raise HTTPException(status_code=400, detail="word is required")
    if not payload.user_prompt.strip():
        raise HTTPException(status_code=400, detail="user_prompt is required")
    if not payload.ai_response.strip():
        raise HTTPException(status_code=400, detail="ai_response is required")

    record = VocabAiExplanation(
        user_id=str(current_user.id),
        card_id=_clean_optional_text(payload.card_id),
        word=word_text,
        user_prompt=payload.user_prompt.strip(),
        ai_response=payload.ai_response.strip(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/vocab/ai-explanations", response_model=list[VocabAiExplanationRead])
@router.get("/words/ai-explanations", response_model=list[VocabAiExplanationRead])
def list_ai_explanations(
    card_id: Optional[str] = Query(default=None, description="Filter by card ID"),
    word: Optional[str] = Query(default=None, description="Filter by word"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Fetch previous AI explanations for the current user."""
    query = select(VocabAiExplanation).where(VocabAiExplanation.user_id == str(current_user.id))
    if card_id and card_id.strip():
        query = query.where(VocabAiExplanation.card_id == card_id.strip())
    if word and word.strip():
        query = query.where(VocabAiExplanation.word.ilike(f"%{word.strip()}%"))

    query = query.order_by(VocabAiExplanation.created_at.desc()).limit(limit)
    return db.exec(query).all()


# ─── Vocabulary Quiz Results Endpoints ────────────────────────────────────────

@router.post("/vocab/quiz-results", response_model=VocabQuizResultRead, status_code=201)
@router.post("/words/quiz-results", response_model=VocabQuizResultRead, status_code=201)
def save_quiz_result(
    payload: VocabQuizResultCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Save a vocabulary quiz attempt result."""
    total_q = max(0, int(payload.total_questions))
    correct_c = max(0, min(total_q, int(payload.correct_count)))
    acc = round(float(payload.accuracy), 2) if payload.accuracy is not None else 0.0
    if total_q > 0 and (acc <= 0.0 or acc > 100.0):
        acc = round((correct_c / total_q) * 100.0, 2)

    record = VocabQuizResult(
        user_id=str(current_user.id),
        total_questions=total_q,
        correct_count=correct_c,
        accuracy=acc,
        voice_used=bool(payload.voice_used),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/vocab/quiz-results", response_model=list[VocabQuizResultRead])
@router.get("/words/quiz-results", response_model=list[VocabQuizResultRead])
def list_quiz_results(
    limit: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Fetch recent quiz results for the current user."""
    query = (
        select(VocabQuizResult)
        .where(VocabQuizResult.user_id == str(current_user.id))
        .order_by(VocabQuizResult.created_at.desc())
        .limit(limit)
    )
    return db.exec(query).all()


# ─── Live Siri-Style AI Globe Vocab Companion Agent ────────────────────────────

class VocabAgentChatRequest(SQLModel):
    message: str
    card_id: Optional[str] = None
    session_id: Optional[str] = None
    voice_mode: bool = True


@router.post("/vocab/agent/chat")
@router.post("/words/agent/chat")
@router.post("/vocab/live-globe")
async def vocab_agent_chat(
    payload: VocabAgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Live Siri-style conversational vocabulary companion agent with memory and user progress context."""
    user_query = payload.message.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="message is required")

    # Fetch user's real vocab statistics & card context from DB
    cards = db.exec(select(Word).where(Word.user_id == current_user.id)).all()
    total_cards = len(cards)
    mastered_count = sum(1 for c in cards if c.box == 5 or c.completed)
    box1_count = sum(1 for c in cards if c.box == 1)
    now_utc = _utc_now()
    due_today_count = sum(1 for c in cards if c.next_review <= now_utc)

    active_card = None
    if payload.card_id:
        active_card = db.get(Word, payload.card_id)

    settings = db.get(UserVocabSettings, current_user.id)
    daily_target = settings.cards_per_day if settings else 5

    # Sample active vocabulary words for immediate context
    sample_words = ", ".join([f"'{c.word}' ({c.meaning})" for c in cards[:8]])

    system_instructions = (
        "You are Aura, an intelligent, motivational, and conversational live AI Vocabulary & English Grammar Companion "
        "for students preparing for competitive exams (PPSC, FPSC, CSS, PMS).\n"
        f"Learner Context:\n"
        f"- Total Cards in Deck: {total_cards}\n"
        f"- Mastered (Box 5): {mastered_count}\n"
        f"- Box 1 (High-Priority / Needs Practice): {box1_count}\n"
        f"- Cards Due for Review: {due_today_count}\n"
        f"- Daily Target: {daily_target} cards/day\n"
        f"- User Deck Sample Words: {sample_words or 'Deck is currently empty'}\n"
        f"{f'- Current Active Card: {active_card.word} ({active_card.meaning})' if active_card else ''}\n\n"
        "Guidelines:\n"
        "1. Tone: Natural, engaging, encouraging, and Siri-like conversational voice.\n"
        "2. If the user asks for a quiz or says 'quiz me', ask ONE punchy multiple-choice question verbally with 3 options (A, B, C) from their deck (or a classic exam word) and prompt them to speak their answer.\n"
        "3. If the user answers a quiz question, immediately evaluate if they are correct, explain why with a mnemonic or usage example, and give encouraging feedback.\n"
        "4. When explaining a word, give its core meaning, a catchy mnemonic hook, and a high-scoring sentence for competitive essay/precis writing.\n"
        "5. Keep replies under 3-4 natural conversational sentences so it reads and speaks out loud cleanly."
    )

    model = get_current_model()
    agent = Agent(
        name="Aura Vocab Companion",
        instructions=system_instructions,
        model=model,
    )

    session_id = payload.session_id or f"vocab_globe_{current_user.id}"
    memory_session = SQLiteSession(session_id, SESSION_DB)

    result = await Runner.run(agent, user_query, session=memory_session)

    # Save discussion record automatically for history & analytics
    try:
        explanation = VocabAiExplanation(
            user_id=str(current_user.id),
            card_id=payload.card_id,
            word=active_card.word if active_card else (user_query[:50]),
            user_prompt=user_query,
            ai_response=result.final_output,
        )
        db.add(explanation)
        db.commit()
    except Exception:
        pass

    return {
        "reply": result.final_output,
        "session_id": session_id,
        "stats": {
            "total": total_cards,
            "mastered": mastered_count,
            "box1": box1_count,
            "due_today": due_today_count,
            "daily_target": daily_target,
        },
    }

