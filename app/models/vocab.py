from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text
from sqlmodel import Field, SQLModel


class Word(SQLModel, table=True):
    __tablename__ = "words"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True),
    )
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    word: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    meaning: str = Field(sa_column=Column(Text, nullable=False))
    relevant_meaning: Optional[str] = Field(default=None, sa_column=Column(Text))
    sentence: Optional[str] = Field(default=None, sa_column=Column(Text))
    hook: Optional[str] = Field(default=None, sa_column=Column(Text))
    synonyms: Optional[str] = Field(default=None, sa_column=Column(Text))
    antonyms: Optional[str] = Field(default=None, sa_column=Column(Text))
    tags: Optional[str] = Field(default=None, sa_column=Column(Text, index=True))
    box: int = Field(default=1, sa_column=Column(Integer, nullable=False, default=1))
    next_review: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    scheduled_date: date = Field(sa_column=Column(Date, nullable=False, index=True))
    completed: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False))
    revision_reminder_sent_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class DayPlan(SQLModel, table=True):
    __tablename__ = "day_plans"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True),
    )
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    plan_date: date = Field(
        default_factory=date.today,
        sa_column=Column("date", Date, nullable=False, unique=True, index=True),
    )
    target_count: int = Field(default=5, sa_column=Column(Integer, nullable=False, default=5))
    due_reminder_sent_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    @property
    def date(self) -> date:
        return self.plan_date

    @date.setter
    def date(self, value: date) -> None:
        self.plan_date = value


class WordCreate(SQLModel):
    word: str
    meaning: str
    relevant_meaning: Optional[str] = None
    sentence: Optional[str] = None
    hook: Optional[str] = None
    synonyms: Optional[str] = None
    antonyms: Optional[str] = None
    tags: Optional[str] = None
    scheduled_date: date


class WordUpdate(SQLModel):
    action: str
    correct: Optional[bool] = None


class WordRead(SQLModel):
    id: str
    user_id: str
    word: str
    meaning: str
    relevant_meaning: Optional[str] = None
    sentence: Optional[str] = None
    hook: Optional[str] = None
    synonyms: Optional[str] = None
    antonyms: Optional[str] = None
    tags: Optional[str] = None
    box: int
    next_review: datetime
    scheduled_date: date
    completed: bool
    revision_reminder_sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DayPlanCreate(SQLModel):
    date: date
    target_count: int = 5


class DayPlanRead(SQLModel):
    id: str
    user_id: str
    date: date
    target_count: int
    due_reminder_sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm(cls, obj: DayPlan):
        return cls(
            id=obj.id,
            user_id=obj.user_id,
            date=obj.plan_date,
            target_count=obj.target_count,
            due_reminder_sent_at=obj.due_reminder_sent_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )
