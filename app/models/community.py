"""
app/models/community.py — MCQ community feature models.
Covers: Favorites, Discussions (threaded), Submissions, Translations.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, Index, Integer, String, Text, Boolean, JSON
from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# MCQ Favorites
# ---------------------------------------------------------------------------
class MCQFavorite(SQLModel, table=True):
    __tablename__ = "mcq_favorites"
    __table_args__ = (
        Index("ix_mcq_favorites_user_mcq", "user_id", "mcq_id", unique=True),
        Index("ix_mcq_favorites_user", "user_id"),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    user_id: str = Field(sa_column=Column(String(36), nullable=False))
    mcq_id: int = Field(nullable=False)
    category_slug: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    mcq_question_preview: Optional[str] = Field(default=None, sa_column=Column(String(200)))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MCQFavoriteCreate(SQLModel):
    mcq_id: int
    category_slug: Optional[str] = None
    mcq_question_preview: Optional[str] = None
    notes: Optional[str] = None


class MCQFavoriteRead(SQLModel):
    id: str
    mcq_id: int
    category_slug: Optional[str]
    mcq_question_preview: Optional[str]
    notes: Optional[str]
    created_at: datetime


# ---------------------------------------------------------------------------
# MCQ Discussions (threaded comments)
# ---------------------------------------------------------------------------
class MCQDiscussion(SQLModel, table=True):
    __tablename__ = "mcq_discussions"
    __table_args__ = (
        Index("ix_mcq_discussions_mcq_created", "mcq_id", "created_at"),
        Index("ix_mcq_discussions_parent", "parent_id"),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    mcq_id: int = Field(nullable=False, index=True)
    user_id: Optional[str] = Field(default=None, sa_column=Column(String(36)))  # null if anonymous
    parent_id: Optional[str] = Field(default=None, sa_column=Column(String(36)))

    author_name: str = Field(sa_column=Column(String(100), nullable=False))
    author_email: Optional[str] = Field(default=None, sa_column=Column(String(255)))  # private, never returned
    author_city: Optional[str] = Field(default=None, sa_column=Column(String(80)))

    body: str = Field(sa_column=Column(Text, nullable=False))
    upvotes: int = Field(default=0)

    is_pinned: bool = Field(default=False)
    is_flagged: bool = Field(default=False)
    is_deleted: bool = Field(default=False)  # soft delete

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MCQDiscussionCreate(SQLModel):
    author_name: str
    author_email: Optional[str] = None
    author_city: Optional[str] = None
    body: str
    parent_id: Optional[str] = None


class MCQDiscussionRead(SQLModel):
    id: str
    mcq_id: int
    parent_id: Optional[str]
    author_name: str
    author_city: Optional[str]
    body: str
    upvotes: int
    is_pinned: bool
    created_at: datetime
    replies: list["MCQDiscussionRead"] = []


# ---------------------------------------------------------------------------
# MCQ Submissions (answer attempts + community stats)
# ---------------------------------------------------------------------------
class MCQSubmission(SQLModel, table=True):
    __tablename__ = "mcq_submissions"
    __table_args__ = (
        Index("ix_mcq_submissions_mcq_option", "mcq_id", "selected_option"),
        Index("ix_mcq_submissions_user", "user_id"),
        Index("ix_mcq_submissions_session", "session_id"),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    mcq_id: int = Field(nullable=False, index=True)
    user_id: Optional[str] = Field(default=None, sa_column=Column(String(36)))
    session_id: Optional[str] = Field(default=None, sa_column=Column(String(120)))  # anonymous session id

    selected_option: str = Field(sa_column=Column(String(1), nullable=False))  # A/B/C/D
    is_correct: bool = Field(default=False)
    time_taken_seconds: Optional[int] = Field(default=None)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MCQSubmissionCreate(SQLModel):
    selected_option: str
    time_taken_seconds: Optional[int] = None
    session_id: Optional[str] = None


class MCQStatsRead(SQLModel):
    mcq_id: int
    total_attempts: int
    correct_rate: float
    distribution: dict[str, dict]
    recent_submitters: list[dict]


# ---------------------------------------------------------------------------
# MCQ Translations (Urdu / other locale cache)
# ---------------------------------------------------------------------------
class MCQTranslation(SQLModel, table=True):
    __tablename__ = "mcq_translations"
    __table_args__ = (
        Index("ix_mcq_translations_mcq_locale", "mcq_id", "locale", unique=True),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    mcq_id: int = Field(nullable=False, index=True)
    locale: str = Field(sa_column=Column(String(10), nullable=False))  # 'ur', 'hi', etc.
    translated_question: str = Field(sa_column=Column(Text, nullable=False))
    translated_options: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    model_used: Optional[str] = Field(default=None, sa_column=Column(String(120)))
    is_verified: bool = Field(default=False)
    verified_by: Optional[str] = Field(default=None, sa_column=Column(String(36)))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MCQTranslationCreate(SQLModel):
    locale: str
    translated_question: str
    translated_options: Optional[dict] = None
    model_used: Optional[str] = None


class MCQTranslationRead(SQLModel):
    id: str
    mcq_id: int
    locale: str
    translated_question: str
    translated_options: Optional[dict]
    model_used: Optional[str]
    is_verified: bool
    created_at: datetime
