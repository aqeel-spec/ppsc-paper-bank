from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, String, JSON
from sqlmodel import Field, SQLModel


class PaperSeriesMode(str, Enum):
    manual = "manual"
    ai = "ai"


class PaperSeriesStatus(str, Enum):
    active = "active"
    paused = "paused"
    completed = "completed"


class PaperSeriesPhase(str, Enum):
    chunk = "chunk"
    half_1 = "half_1"
    half_2 = "half_2"
    final = "final"


class PaperSeries(SQLModel, table=True):
    __tablename__ = "paper_series"

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    title: str = Field(default="Paper Series")
    created_by: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    mode: str = Field(default=PaperSeriesMode.manual, sa_column=Column(String(20), nullable=False))
    years_json: list[int] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    chunk_size: int = Field(default=5)
    status: str = Field(default=PaperSeriesStatus.active, sa_column=Column(String(20), nullable=False))
    start_date: date = Field(nullable=False)
    end_date: Optional[date] = Field(default=None)
    total_papers: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaperSeriesDay(SQLModel, table=True):
    __tablename__ = "paper_series_day"

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    series_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    day_no: int = Field(index=True)
    scheduled_date: date = Field(index=True)
    phase: str = Field(default=PaperSeriesPhase.chunk, sa_column=Column(String(20), nullable=False, index=True))
    syllabus_json: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    paper_id: Optional[int] = Field(default=None, index=True)
    is_locked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaperSeriesAttempt(SQLModel, table=True):
    __tablename__ = "paper_series_attempt"

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    series_day_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    score: Optional[float] = Field(default=None)
    correct_answers: int = Field(default=0)
    total_questions: int = Field(default=0)
    attempt_no: int = Field(default=1)
    credit_cost: int = Field(default=0)
    completed_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaperSeriesRewardLog(SQLModel, table=True):
    __tablename__ = "paper_series_reward_log"

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    series_day_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    rank: int = Field(index=True)
    credits_awarded: int = Field(default=10)
    awarded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaperSeriesCreate(SQLModel):
    title: Optional[str] = None
    mode: str = PaperSeriesMode.manual
    years: list[int]
    chunk_size: int = 5
    start_date: date
    include_half_tests: bool = True
    include_final_test: bool = True


class PaperSeriesRead(SQLModel):
    id: str
    title: str
    mode: str
    years_json: list[int]
    chunk_size: int
    status: str
    start_date: date
    end_date: Optional[date]
    total_papers: int
    created_at: datetime


class PaperSeriesDayRead(SQLModel):
    id: str
    series_id: str
    day_no: int
    scheduled_date: date
    phase: str
    syllabus_json: dict
    paper_id: Optional[int]
    is_locked: bool


class PaperSeriesAttemptStartResponse(SQLModel):
    attempt_id: str
    attempt_no: int
    credit_cost: int
    remaining_credits: int


class PaperSeriesAttemptSubmit(SQLModel):
    attempt_id: str
    score: float
    correct_answers: int
    total_questions: int


class PaperSeriesRewardRead(SQLModel):
    user_id: str
    rank: int
    credits_awarded: int
    awarded_at: datetime
