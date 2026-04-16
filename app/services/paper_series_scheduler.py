from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session, select

from app.database import engine
from app.models.paper_series import PaperSeries, PaperSeriesDay
from app.models.user import User, UserRole
from app.security import create_access_token
from app.services.email_service import broadcast_email_message, is_email_enabled


_scheduler: AsyncIOScheduler | None = None


def _build_admin_token() -> str | None:
    with Session(engine) as db:
        admin = db.exec(select(User).where(User.role == UserRole.admin, User.is_active == True)).first()
        if not admin:
            return None
        return create_access_token({"sub": admin.id})


def _build_syllabus_message(payload: dict) -> str:
    body = payload.get("payload", {})
    day_no = body.get("day_no")
    phase = body.get("phase")
    syllabus = body.get("syllabus", {})
    count = syllabus.get("paper_count", 0)
    years = syllabus.get("years", [])
    return (
        f"PPSC Paper Series\n"
        f"Day {day_no} ({phase})\n"
        f"Years: {', '.join(str(y) for y in years)}\n"
        f"Today's syllabus papers: {count}\n"
        f"Best of luck!"
    )


def _build_syllabus_subject(payload: dict) -> str:
    body = payload.get("payload", {})
    day_no = body.get("day_no")
    return f"PPSC Paper Series - Day {day_no} Syllabus"


def _build_results_message(payload: dict) -> str:
    body = payload.get("payload", {})
    day_no = body.get("day_no")
    phase = body.get("phase")
    participants = body.get("participants", 0)
    leaderboard = body.get("leaderboard", [])
    top_lines = []
    for row in leaderboard[:5]:
        top_lines.append(f"#{row.get('rank')} | user {row.get('user_id')} | score {row.get('score')}")

    top_text = "\n".join(top_lines) if top_lines else "No submissions today"
    return (
        f"PPSC Paper Series Results\n"
        f"Day {day_no} ({phase})\n"
        f"Participants: {participants}\n"
        f"Top Board:\n{top_text}\n"
        f"Top 5 get +10 credits"
    )


def _build_results_subject(payload: dict) -> str:
    body = payload.get("payload", {})
    day_no = body.get("day_no")
    return f"PPSC Paper Series - Day {day_no} Results"


def _get_creator_email_for_day(day_id: str) -> str | None:
    with Session(engine) as db:
        day = db.get(PaperSeriesDay, day_id)
        if not day:
            return None

        series = db.get(PaperSeries, day.series_id)
        if not series:
            return None

        creator = db.get(User, series.created_by)
        if not creator or not creator.email:
            return None

        return creator.email.strip().lower()


async def _dispatch_for_date(target_date: date, endpoint_suffix: str) -> None:
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    token = _build_admin_token()
    if not token:
        print("⚠️ Scheduler skipped: admin user not found")
        return

    with Session(engine) as db:
        day_ids = [
            row.id
            for row in db.exec(select(PaperSeriesDay).where(PaperSeriesDay.scheduled_date == target_date)).all()
        ]

    if not day_ids:
        print(f"ℹ️ Scheduler: no paper-series day for {target_date}")
        return

    headers = {"Authorization": f"Bearer {token}"}
    timeout = httpx.Timeout(20.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for day_id in day_ids:
            url = f"{api_base}/paper-series/day/{day_id}/{endpoint_suffix}"
            try:
                resp = await client.post(url, headers=headers)
            except Exception as exc:
                # If API_BASE_URL server is not running, call endpoints against ASGI app directly.
                try:
                    from main import app

                    transport = httpx.ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://internal", timeout=timeout) as internal_client:
                        resp = await internal_client.post(
                            f"/paper-series/day/{day_id}/{endpoint_suffix}",
                            headers=headers,
                        )
                except Exception as fallback_exc:
                    print(f"⚠️ Scheduler error on {url}: {exc}; fallback failed: {fallback_exc}")
                    continue

            if resp.status_code >= 400:
                print(f"⚠️ Scheduler request failed [{resp.status_code}] {url}: {resp.text[:180]}")
                continue

            payload = resp.json()
            if is_email_enabled():
                if endpoint_suffix == "dispatch-syllabus":
                    subject = _build_syllabus_subject(payload)
                    message = _build_syllabus_message(payload)
                else:
                    subject = _build_results_subject(payload)
                    message = _build_results_message(payload)
                creator_email = _get_creator_email_for_day(day_id)
                recipients = [creator_email] if creator_email else None
                email_result = broadcast_email_message(subject, message, recipients=recipients)
                print(f"Email broadcast: {email_result}")
            else:
                print(f"Email disabled. Payload prepared for {endpoint_suffix}: day={day_id}")


async def _job_syllabus() -> None:
    await _dispatch_for_date(date.today(), "dispatch-syllabus")


async def _job_results() -> None:
    await _dispatch_for_date(date.today(), "dispatch-results")


def start_paper_series_scheduler() -> None:
    global _scheduler
    if os.getenv("PAPER_SERIES_SCHEDULER_ENABLED", "1") != "1":
        print("ℹ️ Paper series scheduler disabled by PAPER_SERIES_SCHEDULER_ENABLED")
        return

    if _scheduler and _scheduler.running:
        return

    timezone = os.getenv("PAPER_SERIES_SCHEDULER_TZ", "Asia/Karachi")
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(_job_syllabus, "cron", hour=1, minute=0, id="paper_series_syllabus_1am")
    scheduler.add_job(_job_results, "cron", hour=23, minute=58, id="paper_series_results_2358")
    scheduler.start()

    _scheduler = scheduler
    print(f"✅ Paper series scheduler started ({timezone})")


def stop_paper_series_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("🛑 Paper series scheduler stopped")
    _scheduler = None


def run_scheduler_once_for_test() -> dict:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_job_syllabus())
    loop.run_until_complete(_job_results())
    return {"ok": True}
