from datetime import date, datetime, timedelta, timezone
from statistics import mean

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select, func

from app.database import get_session
from app.models.paper import PaperModel
from app.models.paper_series import (
    PaperSeries,
    PaperSeriesAttempt,
    PaperSeriesAttemptStartResponse,
    PaperSeriesAttemptSubmit,
    PaperSeriesCreate,
    PaperSeriesDay,
    PaperSeriesDayRead,
    PaperSeriesPhase,
    PaperSeriesRead,
    PaperSeriesRewardLog,
    PaperSeriesRewardRead,
)
from app.models.user import User, UserRole
from app.security import get_current_user, require_admin


router = APIRouter(prefix="/paper-series", tags=["Paper Series"])


def _chunk_ids(paper_ids: list[int], chunk_size: int) -> list[list[int]]:
    return [paper_ids[i : i + chunk_size] for i in range(0, len(paper_ids), chunk_size)]


def _to_day_syllabus(phase: str, paper_ids: list[int], years: list[int]) -> dict:
    return {
        "phase": phase,
        "paper_ids": paper_ids,
        "years": years,
        "paper_count": len(paper_ids),
    }


@router.get("/meta/years")
def get_year_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    rows = db.exec(
        select(PaperModel.year, func.count(PaperModel.id))
        .where(PaperModel.year.is_not(None))
        .group_by(PaperModel.year)
        .order_by(PaperModel.year.desc())
    ).all()

    years = [
        {"year": int(year), "paper_count": int(count)}
        for year, count in rows
        if year is not None
    ]
    return {
        "years": years,
        "total_papers": int(sum(item["paper_count"] for item in years)),
    }


@router.post("", response_model=PaperSeriesRead, status_code=201)
def create_series(
    body: PaperSeriesCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    years = sorted({int(y) for y in body.years})
    if not years:
        raise HTTPException(status_code=400, detail="At least one year is required")
    if body.chunk_size < 1:
        raise HTTPException(status_code=400, detail="chunk_size must be >= 1")

    papers = db.exec(
        select(PaperModel)
        .where(PaperModel.year.in_(years))
        .order_by(PaperModel.year.asc(), PaperModel.id.asc())
    ).all()
    if not papers:
        raise HTTPException(status_code=404, detail="No papers found for selected year(s)")

    paper_ids = [p.id for p in papers if p.id is not None]
    total = len(paper_ids)
    auto_title = f"PPSC Series {'/'.join(str(y) for y in years)} - {body.start_date.isoformat()}"

    series = PaperSeries(
        title=(body.title.strip() if isinstance(body.title, str) and body.title.strip() else auto_title),
        created_by=current_user.id,
        mode=body.mode,
        years_json=years,
        chunk_size=body.chunk_size,
        start_date=body.start_date,
        total_papers=total,
    )
    db.add(series)
    db.flush()

    day_no = 1
    date_cursor = body.start_date

    for chunk in _chunk_ids(paper_ids, body.chunk_size):
        db.add(
            PaperSeriesDay(
                series_id=series.id,
                day_no=day_no,
                scheduled_date=date_cursor,
                phase=PaperSeriesPhase.chunk,
                syllabus_json=_to_day_syllabus(PaperSeriesPhase.chunk, chunk, years),
            )
        )
        day_no += 1
        date_cursor += timedelta(days=1)

    if body.include_half_tests:
        half = max(1, total // 2)
        first_half = paper_ids[:half]
        second_half = paper_ids[half:] if half < total else paper_ids

        db.add(
            PaperSeriesDay(
                series_id=series.id,
                day_no=day_no,
                scheduled_date=date_cursor,
                phase=PaperSeriesPhase.half_1,
                syllabus_json=_to_day_syllabus(PaperSeriesPhase.half_1, first_half, years),
            )
        )
        day_no += 1
        date_cursor += timedelta(days=1)

        db.add(
            PaperSeriesDay(
                series_id=series.id,
                day_no=day_no,
                scheduled_date=date_cursor,
                phase=PaperSeriesPhase.half_2,
                syllabus_json=_to_day_syllabus(PaperSeriesPhase.half_2, second_half, years),
            )
        )
        day_no += 1
        date_cursor += timedelta(days=1)

    if body.include_final_test:
        db.add(
            PaperSeriesDay(
                series_id=series.id,
                day_no=day_no,
                scheduled_date=date_cursor,
                phase=PaperSeriesPhase.final,
                syllabus_json=_to_day_syllabus(PaperSeriesPhase.final, paper_ids, years),
            )
        )
        series.end_date = date_cursor
    else:
        series.end_date = date_cursor - timedelta(days=1)

    db.add(series)
    db.commit()
    db.refresh(series)
    return series


@router.get("", response_model=list[PaperSeriesRead])
def list_series(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    stmt = select(PaperSeries)
    if current_user.role != UserRole.admin:
        stmt = stmt.where(PaperSeries.created_by == current_user.id)

    return db.exec(
        stmt.order_by(PaperSeries.created_at.desc()).offset(offset).limit(limit)
    ).all()


@router.get("/{series_id}", response_model=PaperSeriesRead)
def get_series(
    series_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    series = db.get(PaperSeries, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    if current_user.role != UserRole.admin and series.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    return series


@router.get("/{series_id}/days", response_model=list[PaperSeriesDayRead])
def list_series_days(
    series_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    series = db.get(PaperSeries, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    if current_user.role != UserRole.admin and series.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    return db.exec(
        select(PaperSeriesDay)
        .where(PaperSeriesDay.series_id == series_id)
        .order_by(PaperSeriesDay.day_no.asc())
    ).all()


@router.get("/{series_id}/today", response_model=PaperSeriesDayRead)
def get_today_syllabus(
    series_id: str,
    for_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    series = db.get(PaperSeries, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    if current_user.role != UserRole.admin and series.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    target_date = for_date or date.today()
    row = db.exec(
        select(PaperSeriesDay)
        .where(PaperSeriesDay.series_id == series_id, PaperSeriesDay.scheduled_date == target_date)
        .order_by(PaperSeriesDay.day_no.asc())
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="No series day found for date")
    return row


@router.post("/day/{day_id}/start", response_model=PaperSeriesAttemptStartResponse, status_code=201)
def start_day_attempt(
    day_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    day = db.get(PaperSeriesDay, day_id)
    if not day:
        raise HTTPException(status_code=404, detail="Series day not found")

    attempts = db.exec(
        select(PaperSeriesAttempt)
        .where(PaperSeriesAttempt.series_day_id == day_id, PaperSeriesAttempt.user_id == current_user.id)
        .order_by(PaperSeriesAttempt.attempt_no.asc())
    ).all()

    next_attempt_no = len(attempts) + 1
    if next_attempt_no == 1:
        cost = 0
    elif next_attempt_no == 2:
        cost = 2
    else:
        raise HTTPException(status_code=409, detail="Attempt limit reached for this day")

    is_admin = current_user.role == UserRole.admin
    if not is_admin and cost > 0:
        if current_user.credits < cost:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"{cost} credits required for second attempt",
            )
        current_user.credits -= cost
        db.add(current_user)

    attempt = PaperSeriesAttempt(
        series_day_id=day_id,
        user_id=current_user.id,
        attempt_no=next_attempt_no,
        credit_cost=cost,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return PaperSeriesAttemptStartResponse(
        attempt_id=attempt.id,
        attempt_no=attempt.attempt_no,
        credit_cost=attempt.credit_cost,
        remaining_credits=current_user.credits,
    )


@router.post("/day/{day_id}/submit")
def submit_day_attempt(
    day_id: str,
    body: PaperSeriesAttemptSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    day = db.get(PaperSeriesDay, day_id)
    if not day:
        raise HTTPException(status_code=404, detail="Series day not found")

    attempt = db.get(PaperSeriesAttempt, body.attempt_id)
    if not attempt or attempt.series_day_id != day_id or attempt.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Attempt not found")

    if attempt.completed_at is not None:
        raise HTTPException(status_code=409, detail="Attempt already submitted")

    attempt.score = round(float(body.score), 2)
    attempt.correct_answers = int(body.correct_answers)
    attempt.total_questions = int(body.total_questions)
    attempt.completed_at = datetime.now(timezone.utc)
    db.add(attempt)

    if attempt.attempt_no == 1:
        day.is_locked = True
        db.add(day)

    db.commit()
    return {
        "attempt_id": attempt.id,
        "score": attempt.score,
        "correct_answers": attempt.correct_answers,
        "total_questions": attempt.total_questions,
        "completed_at": attempt.completed_at,
    }


@router.get("/{series_id}/leaderboard")
def get_day_leaderboard(
    series_id: str,
    day_no: int = Query(..., ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    series = db.get(PaperSeries, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    if current_user.role != UserRole.admin and series.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    day = db.exec(
        select(PaperSeriesDay).where(PaperSeriesDay.series_id == series_id, PaperSeriesDay.day_no == day_no)
    ).first()
    if not day:
        raise HTTPException(status_code=404, detail="Series day not found")

    attempts = db.exec(
        select(PaperSeriesAttempt)
        .where(PaperSeriesAttempt.series_day_id == day.id, PaperSeriesAttempt.completed_at.is_not(None))
    ).all()

    best_by_user: dict[str, PaperSeriesAttempt] = {}
    for a in attempts:
        existing = best_by_user.get(a.user_id)
        if not existing:
            best_by_user[a.user_id] = a
            continue
        if (a.score or 0.0) > (existing.score or 0.0):
            best_by_user[a.user_id] = a
        elif (a.score or 0.0) == (existing.score or 0.0):
            if (a.completed_at or datetime.max.replace(tzinfo=timezone.utc)) < (
                existing.completed_at or datetime.max.replace(tzinfo=timezone.utc)
            ):
                best_by_user[a.user_id] = a

    ranked = sorted(
        best_by_user.values(),
        key=lambda x: (-(x.score or 0.0), -x.correct_answers, x.completed_at or datetime.max.replace(tzinfo=timezone.utc)),
    )

    return {
        "series_id": series_id,
        "day_id": day.id,
        "day_no": day_no,
        "phase": day.phase,
        "leaderboard": [
            {
                "rank": idx + 1,
                "user_id": a.user_id,
                "score": a.score,
                "correct_answers": a.correct_answers,
                "total_questions": a.total_questions,
                "attempt_no": a.attempt_no,
                "completed_at": a.completed_at,
            }
            for idx, a in enumerate(ranked)
        ],
    }


@router.post("/day/{day_id}/award-top5", response_model=list[PaperSeriesRewardRead])
def award_top5(
    day_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    day = db.get(PaperSeriesDay, day_id)
    if not day:
        raise HTTPException(status_code=404, detail="Series day not found")

    existing_rewards = db.exec(
        select(PaperSeriesRewardLog)
        .where(PaperSeriesRewardLog.series_day_id == day_id)
        .order_by(PaperSeriesRewardLog.rank.asc())
    ).all()
    if existing_rewards:
        return existing_rewards

    attempts = db.exec(
        select(PaperSeriesAttempt)
        .where(PaperSeriesAttempt.series_day_id == day_id, PaperSeriesAttempt.completed_at.is_not(None))
    ).all()

    best_by_user: dict[str, PaperSeriesAttempt] = {}
    for a in attempts:
        existing = best_by_user.get(a.user_id)
        if not existing or (a.score or 0.0) > (existing.score or 0.0):
            best_by_user[a.user_id] = a

    ranked = sorted(
        best_by_user.values(),
        key=lambda x: (-(x.score or 0.0), -x.correct_answers, x.completed_at or datetime.max.replace(tzinfo=timezone.utc)),
    )[:5]

    rewards: list[PaperSeriesRewardLog] = []
    for idx, entry in enumerate(ranked):
        user = db.get(User, entry.user_id)
        if user:
            user.credits += 10
            db.add(user)

        reward = PaperSeriesRewardLog(
            series_day_id=day_id,
            user_id=entry.user_id,
            rank=idx + 1,
            credits_awarded=10,
        )
        db.add(reward)
        rewards.append(reward)

    db.commit()
    for r in rewards:
        db.refresh(r)
    return rewards


@router.post("/day/{day_id}/dispatch-syllabus")
def dispatch_syllabus_payload(
    day_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    day = db.get(PaperSeriesDay, day_id)
    if not day:
        raise HTTPException(status_code=404, detail="Series day not found")

    return {
        "series_day_id": day.id,
        "scheduled_dispatch_time": "01:00",
        "message_type": "syllabus",
        "payload": {
            "day_no": day.day_no,
            "phase": day.phase,
            "scheduled_date": day.scheduled_date,
            "syllabus": day.syllabus_json,
        },
        "note": "Connect this payload to your email provider worker",
    }


@router.post("/day/{day_id}/dispatch-results")
def dispatch_results_payload(
    day_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    day = db.get(PaperSeriesDay, day_id)
    if not day:
        raise HTTPException(status_code=404, detail="Series day not found")

    attempts = db.exec(
        select(PaperSeriesAttempt)
        .where(PaperSeriesAttempt.series_day_id == day_id, PaperSeriesAttempt.completed_at.is_not(None))
    ).all()

    best_by_user: dict[str, PaperSeriesAttempt] = {}
    for a in attempts:
        existing = best_by_user.get(a.user_id)
        if not existing or (a.score or 0.0) > (existing.score or 0.0):
            best_by_user[a.user_id] = a

    ranked = sorted(
        best_by_user.values(),
        key=lambda x: (-(x.score or 0.0), -x.correct_answers, x.completed_at or datetime.max.replace(tzinfo=timezone.utc)),
    )

    return {
        "series_day_id": day.id,
        "scheduled_dispatch_time": "23:58",
        "message_type": "results",
        "payload": {
            "day_no": day.day_no,
            "phase": day.phase,
            "participants": len(best_by_user),
            "leaderboard": [
                {
                    "rank": idx + 1,
                    "user_id": row.user_id,
                    "score": row.score,
                    "correct_answers": row.correct_answers,
                }
                for idx, row in enumerate(ranked)
            ],
        },
        "note": "Connect this payload to your email provider worker",
    }


@router.get("/{series_id}/progress")
def get_series_progress(
    series_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    series = db.get(PaperSeries, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    if current_user.role != UserRole.admin and series.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    days = db.exec(
        select(PaperSeriesDay)
        .where(PaperSeriesDay.series_id == series_id)
        .order_by(PaperSeriesDay.day_no.asc())
    ).all()
    attempts = db.exec(
        select(PaperSeriesAttempt).where(PaperSeriesAttempt.series_day_id.in_([d.id for d in days]))
    ).all() if days else []

    completed_attempts = [a for a in attempts if a.completed_at is not None]
    users = {a.user_id for a in attempts}

    return {
        "series_id": series.id,
        "status": series.status,
        "total_papers": series.total_papers,
        "total_days": len(days),
        "completed_days": sum(1 for d in days if d.scheduled_date <= date.today()),
        "total_participants": len(users),
        "total_attempts": len(attempts),
        "completed_attempts": len(completed_attempts),
        "average_score": round(mean([a.score for a in completed_attempts if a.score is not None]), 2)
        if completed_attempts
        else 0.0,
    }


@router.get("/{series_id}/graphs")
def get_series_graphs(
    series_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    series = db.get(PaperSeries, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    if current_user.role != UserRole.admin and series.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    days = db.exec(
        select(PaperSeriesDay)
        .where(PaperSeriesDay.series_id == series_id)
        .order_by(PaperSeriesDay.day_no.asc())
    ).all()

    day_rows = []
    for d in days:
        attempts = db.exec(select(PaperSeriesAttempt).where(PaperSeriesAttempt.series_day_id == d.id)).all()
        completed = [a for a in attempts if a.completed_at is not None and a.score is not None]
        day_rows.append(
            {
                "day_no": d.day_no,
                "date": d.scheduled_date,
                "phase": d.phase,
                "participants": len({a.user_id for a in attempts}),
                "attempts": len(attempts),
                "avg_score": round(mean([a.score for a in completed]), 2) if completed else 0.0,
                "top_score": max([a.score for a in completed], default=0.0),
            }
        )

    return {
        "series_id": series_id,
        "coverage": {
            "total_days": len(days),
            "completed_days": sum(1 for d in days if d.scheduled_date <= date.today()),
            "total_papers": series.total_papers,
        },
        "trend": day_rows,
    }
