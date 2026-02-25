"""
app/routes/users.py — User profile, dashboard, favorites, goals, and learning tracking.
"""
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select, func

from app.database import get_session
from app.models.user import User, UserRead, UserUpdate
from app.models.community import MCQFavorite, MCQFavoriteCreate, MCQFavoriteRead, MCQSubmission
from app.models.learning import (
    LearningActivity, LearningActivityRead, LearningGoal, LearningGoalCreate,
    LearningGoalRead, StudyStreak, StudyStreakRead, ActivityType,
)
from app.security import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@router.get("/me/dashboard")
def dashboard(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    streak = session.exec(select(StudyStreak).where(StudyStreak.user_id == current_user.id)).one_or_none()
    goals = session.exec(
        select(LearningGoal)
        .where(LearningGoal.user_id == current_user.id, LearningGoal.status == "active")
        .limit(5)
    ).all()
    recent = session.exec(
        select(LearningActivity)
        .where(LearningActivity.user_id == current_user.id)
        .order_by(LearningActivity.logged_at.desc())
        .limit(10)
    ).all()
    favorites_count = session.exec(
        select(func.count(MCQFavorite.id)).where(MCQFavorite.user_id == current_user.id)
    ).one()

    return {
        "user": {"id": current_user.id, "username": current_user.username, "credits": current_user.credits},
        "streak": {
            "current": streak.current_streak if streak else 0,
            "longest": streak.longest_streak if streak else 0,
            "total_points": streak.total_points if streak else 0,
        },
        "active_goals_count": len(goals),
        "favorites_count": favorites_count,
        "recent_activity": [
            {"type": a.activity_type, "points": a.points, "at": a.logged_at} for a in recent
        ],
    }


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@router.patch("/me", response_model=UserRead)
def update_profile(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(current_user, k, v)
    current_user.updated_at = datetime.now(timezone.utc)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------
@router.get("/me/credits")
def get_credits(current_user: User = Depends(get_current_user)):
    return {"credits": current_user.credits}


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------
@router.get("/me/favorites")
def list_favorites(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
):
    items = session.exec(
        select(MCQFavorite)
        .where(MCQFavorite.user_id == current_user.id)
        .order_by(MCQFavorite.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    total = session.exec(
        select(func.count(MCQFavorite.id)).where(MCQFavorite.user_id == current_user.id)
    ).one()
    return {"count": total, "items": items}


@router.post("/me/favorites", status_code=201)
def add_favorite(
    body: MCQFavoriteCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    existing = session.exec(
        select(MCQFavorite).where(
            MCQFavorite.user_id == current_user.id,
            MCQFavorite.mcq_id == body.mcq_id,
        )
    ).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="MCQ already in favorites")

    fav = MCQFavorite(user_id=current_user.id, **body.model_dump())
    session.add(fav)
    # Log activity
    _log_activity(session, current_user.id, ActivityType.favorite_added)
    session.commit()
    session.refresh(fav)
    return fav


@router.delete("/me/favorites/{mcq_id}", status_code=204)
def remove_favorite(
    mcq_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    fav = session.exec(
        select(MCQFavorite).where(MCQFavorite.user_id == current_user.id, MCQFavorite.mcq_id == mcq_id)
    ).one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="Favorite not found")
    session.delete(fav)
    session.commit()


@router.get("/me/favorites/count")
def favorites_count(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    count = session.exec(
        select(func.count(MCQFavorite.id)).where(MCQFavorite.user_id == current_user.id)
    ).one()
    return {"count": count}


# ---------------------------------------------------------------------------
# Answer history
# ---------------------------------------------------------------------------
@router.get("/me/history")
def answer_history(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
):
    submissions = session.exec(
        select(MCQSubmission)
        .where(MCQSubmission.user_id == current_user.id)
        .order_by(MCQSubmission.submitted_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    total = session.exec(
        select(func.count(MCQSubmission.id)).where(MCQSubmission.user_id == current_user.id)
    ).one()
    return {"total": total, "items": submissions}


# ---------------------------------------------------------------------------
# Learning goals
# ---------------------------------------------------------------------------
@router.get("/me/goals", response_model=list[LearningGoalRead])
def list_goals(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(LearningGoal).where(LearningGoal.user_id == current_user.id)
    ).all()


@router.post("/me/goals", response_model=LearningGoalRead, status_code=201)
def create_goal(
    body: LearningGoalCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    goal = LearningGoal(user_id=current_user.id, **body.model_dump())
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


@router.patch("/me/goals/{goal_id}", response_model=LearningGoalRead)
def update_goal(
    goal_id: str,
    body: LearningGoalCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    goal = session.exec(
        select(LearningGoal)
        .where(LearningGoal.id == goal_id, LearningGoal.user_id == current_user.id)
    ).one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(goal, k, v)
    goal.updated_at = datetime.now(timezone.utc)
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


# ---------------------------------------------------------------------------
# Streak
# ---------------------------------------------------------------------------
@router.get("/me/streak", response_model=StudyStreakRead)
def get_streak(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    streak = session.get(StudyStreak, current_user.id)
    if not streak:
        return StudyStreakRead(current_streak=0, longest_streak=0, total_days_active=0, total_points=0, last_activity_date=None)
    return streak


# ---------------------------------------------------------------------------
# Internal: log activity + update streak
# ---------------------------------------------------------------------------
def _log_activity(session: Session, user_id: str, activity_type: ActivityType, points: int = 1, category_slug: Optional[str] = None):
    """Log a learning event and update study streak."""
    entry = LearningActivity(user_id=user_id, activity_type=activity_type, points=points, category_slug=category_slug)
    session.add(entry)

    # Update streak
    today = date.today()
    streak = session.get(StudyStreak, user_id)
    if not streak:
        streak = StudyStreak(user_id=user_id, current_streak=1, longest_streak=1, total_days_active=1, total_points=points, last_activity_date=today)
    else:
        if streak.last_activity_date != today:
            from datetime import timedelta
            if streak.last_activity_date and (today - streak.last_activity_date).days == 1:
                streak.current_streak += 1
            else:
                streak.current_streak = 1
            streak.total_days_active += 1
            streak.last_activity_date = today
        streak.total_points += points
        if streak.current_streak > streak.longest_streak:
            streak.longest_streak = streak.current_streak
    session.add(streak)
