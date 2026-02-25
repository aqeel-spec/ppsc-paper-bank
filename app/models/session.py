"""
app/models/session.py — Mock session and daily paper models.
"""
from datetime import datetime, date, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, Date, Integer, String, Text, Boolean, Float
from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Mock Session
# ---------------------------------------------------------------------------
class MockSessionStatus(str, Enum):
    pending = "pending"
    started = "started"
    completed = "completed"
    abandoned = "abandoned"


class MockSession(SQLModel, table=True):
    __tablename__ = "mock_sessions"

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    paper_id: Optional[int] = Field(default=None)  # FK to PaperModel

    status: str = Field(default=MockSessionStatus.pending, sa_column=Column(String(20), default="pending"))
    score: Optional[float] = Field(default=None)           # percentage (0-100)
    total_questions: int = Field(default=0)
    correct_answers: int = Field(default=0)

    credit_used: bool = Field(default=True)                # whether this consumed a credit
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MockSessionCreate(SQLModel):
    paper_id: Optional[int] = None


class MockSessionRead(SQLModel):
    id: str
    user_id: str
    paper_id: Optional[int]
    status: str
    score: Optional[float]
    total_questions: int
    correct_answers: int
    credit_used: bool
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


# ---------------------------------------------------------------------------
# Mock Session Answers
# ---------------------------------------------------------------------------
class MockSessionAnswer(SQLModel, table=True):
    __tablename__ = "mock_session_answers"

    id: int = Field(default=None, primary_key=True)
    session_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    mcq_id: int = Field(nullable=False)
    selected_option: Optional[str] = Field(default=None, sa_column=Column(String(1)))
    is_correct: Optional[bool] = Field(default=None)
    time_taken_seconds: Optional[int] = Field(default=None)
    answered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MockSessionAnswerCreate(SQLModel):
    mcq_id: int
    selected_option: str
    time_taken_seconds: Optional[int] = None


# ---------------------------------------------------------------------------
# Daily Paper
# ---------------------------------------------------------------------------
class DailyPaper(SQLModel, table=True):
    __tablename__ = "daily_papers"

    id: int = Field(default=None, primary_key=True)
    paper_date: date = Field(sa_column=Column(Date, unique=True, nullable=False, index=True))
    paper_id: int = Field(nullable=False)              # FK to PaperModel
    is_active: bool = Field(default=True)
    created_by: Optional[str] = Field(default=None, sa_column=Column(String(36)))  # admin user id
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DailyPaperRead(SQLModel):
    id: int
    paper_date: date
    paper_id: int
    is_active: bool


# ---------------------------------------------------------------------------
# Daily Paper Attempts
# ---------------------------------------------------------------------------
class DailyPaperAttempt(SQLModel, table=True):
    __tablename__ = "daily_paper_attempts"

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    daily_paper_id: int = Field(nullable=False, index=True)
    score: Optional[float] = Field(default=None)
    total_questions: int = Field(default=0)
    correct_answers: int = Field(default=0)
    completed_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DailyPaperAttemptRead(SQLModel):
    id: str
    daily_paper_id: int
    score: Optional[float]
    total_questions: int
    correct_answers: int
    completed_at: Optional[datetime]
    created_at: datetime
