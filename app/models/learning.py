"""
app/models/learning.py — Learning goals, activity log, and streak tracking.
"""
from datetime import datetime, date, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, Date, String, Text, Integer, Boolean
from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Learning Goal
# ---------------------------------------------------------------------------
class GoalStatus(str, Enum):
    active = "active"
    completed = "completed"
    paused = "paused"


class LearningGoal(SQLModel, table=True):
    __tablename__ = "learning_goals"

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    title: str = Field(sa_column=Column(String(255), nullable=False))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    target_date: Optional[date] = Field(default=None, sa_column=Column(Date))
    daily_target_minutes: int = Field(default=30)
    status: str = Field(default=GoalStatus.active, sa_column=Column(String(20), default="active"))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LearningGoalCreate(SQLModel):
    title: str
    description: Optional[str] = None
    target_date: Optional[date] = None
    daily_target_minutes: int = 30


class LearningGoalRead(SQLModel):
    id: str
    title: str
    description: Optional[str]
    target_date: Optional[date]
    daily_target_minutes: int
    status: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Learning Activity log — individual events
# ---------------------------------------------------------------------------
class ActivityType(str, Enum):
    mcq_attempt = "mcq_attempt"
    mock_session = "mock_session"
    daily_paper = "daily_paper"
    discussion_post = "discussion_post"
    favorite_added = "favorite_added"
    login = "login"


class LearningActivity(SQLModel, table=True):
    __tablename__ = "learning_activities"

    id: int = Field(default=None, primary_key=True)
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    activity_type: str = Field(sa_column=Column(String(30), nullable=False))
    category_slug: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    reference_id: Optional[str] = Field(default=None, sa_column=Column(String(36)))  # mcq_id, session_id, etc.
    points: int = Field(default=1)  # gamification points per activity
    logged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LearningActivityRead(SQLModel):
    id: int
    activity_type: str
    category_slug: Optional[str]
    points: int
    logged_at: datetime


# ---------------------------------------------------------------------------
# Study Streak — daily activity streak per user
# ---------------------------------------------------------------------------
class StudyStreak(SQLModel, table=True):
    __tablename__ = "study_streaks"

    user_id: str = Field(sa_column=Column(String(36), primary_key=True))
    current_streak: int = Field(default=0)
    longest_streak: int = Field(default=0)
    total_days_active: int = Field(default=0)
    total_points: int = Field(default=0)
    last_activity_date: Optional[date] = Field(default=None, sa_column=Column(Date))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StudyStreakRead(SQLModel):
    current_streak: int
    longest_streak: int
    total_days_active: int
    total_points: int
    last_activity_date: Optional[date]
