"""
Database models for the Mock Interview Panel system.

Tables
------
interview_session          — one row per interview session
interview_message          — every message exchanged (candidate + interviewer)
interview_feedback         — AI-generated feedback reports
interview_question_score   — per-question AI score in structured interviews
"""

from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Column, DateTime, Float, Text
from sqlalchemy.sql import func
from sqlmodel import Field, Relationship, SQLModel


# ── Enums ──────────────────────────────────────────────────────────────────


class InterviewMode(str, PyEnum):
    """Whether the session is a single-avatar or full-panel interview."""
    single = "single"
    panel = "panel"
    structured = "structured"


class MessageRole(str, PyEnum):
    """Who sent the message."""
    candidate = "candidate"
    interviewer = "interviewer"
    system = "system"


class SessionStatus(str, PyEnum):
    """Lifecycle status of a session."""
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


# ── Table models ───────────────────────────────────────────────────────────


class InterviewSession(SQLModel, table=True):
    """Tracks a single interview session (one or panel mode)."""

    __tablename__ = "interview_session"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, unique=True, max_length=255)
    candidate_name: Optional[str] = Field(default=None, max_length=255)
    avatar: str = Field(max_length=50, description="Avatar type or 'panel'.")
    subject: Optional[str] = Field(default=None, max_length=255)
    mode: str = Field(
        default=InterviewMode.single.value,
        max_length=20,
        description="single | panel | structured",
    )
    status: str = Field(
        default=SessionStatus.active.value,
        max_length=20,
        description="active | completed | abandoned",
    )
    total_messages: int = Field(default=0)

    # ── Structured interview tracking fields ──
    questions_per_avatar: int = Field(
        default=3,
        description="Number of questions each avatar asks in structured mode.",
    )
    current_avatar_index: int = Field(
        default=0,
        description="Index (0-3) of the avatar currently asking questions.",
    )
    current_question_index: int = Field(
        default=0,
        description="Global 0-based index of the next question to ask.",
    )
    total_questions: int = Field(
        default=12,
        description="Total questions planned (avatars × questions_per_avatar).",
    )
    overall_score: Optional[float] = Field(
        default=None,
        description="Normalised overall score (0-100) computed at finish.",
    )

    started_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )
    ended_at: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(
            DateTime,
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )

    # Relationships
    messages: List["InterviewMessage"] = Relationship(back_populates="session")
    feedbacks: List["InterviewFeedback"] = Relationship(back_populates="session")
    question_scores: List["InterviewQuestionScore"] = Relationship(back_populates="session")


class InterviewMessage(SQLModel, table=True):
    """Every message exchanged during an interview session."""

    __tablename__ = "interview_message"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, foreign_key="interview_session.session_id", max_length=255)
    role: str = Field(
        max_length=20,
        description="candidate | interviewer | system",
    )
    avatar: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Which avatar sent this message (null for candidate).",
    )
    content: str = Field(sa_column=Column(Text, nullable=False))
    message_index: int = Field(
        default=0,
        description="0-based order within the session.",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )

    # Relationship
    session: Optional[InterviewSession] = Relationship(back_populates="messages")


class InterviewFeedback(SQLModel, table=True):
    """AI-generated feedback report for a session."""

    __tablename__ = "interview_feedback"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, foreign_key="interview_session.session_id", max_length=255)
    feedback: str = Field(sa_column=Column(Text, nullable=False))
    overall_score: Optional[int] = Field(
        default=None,
        description="Extracted overall score (0-100), if parseable.",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )

    # Relationship
    session: Optional[InterviewSession] = Relationship(back_populates="feedbacks")


class InterviewQuestionScore(SQLModel, table=True):
    """Per-question AI score for structured interviews."""

    __tablename__ = "interview_question_score"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, foreign_key="interview_session.session_id", max_length=255)
    question_index: int = Field(
        description="Global 0-based question number in the interview.",
    )
    avatar: str = Field(max_length=50, description="Avatar that asked this question.")
    question_text: str = Field(sa_column=Column(Text, nullable=False))
    answer_text: str = Field(sa_column=Column(Text, nullable=False))
    score: float = Field(
        description="AI-assigned score for this answer (0-100).",
    )
    ai_feedback: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Brief AI feedback on this specific answer.",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, server_default=func.now(), nullable=False),
    )

    # Relationship
    session: Optional[InterviewSession] = Relationship(back_populates="question_scores")


# ── Pydantic (non-table) schemas for API responses ────────────────────────


class InterviewSessionRead(SQLModel):
    """Public read schema for a session."""
    id: Optional[int] = None
    session_id: str
    candidate_name: Optional[str] = None
    avatar: str
    subject: Optional[str] = None
    mode: str
    status: str
    total_messages: int = 0
    questions_per_avatar: int = 3
    current_avatar_index: int = 0
    current_question_index: int = 0
    total_questions: int = 12
    overall_score: Optional[float] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class InterviewMessageRead(SQLModel):
    """Public read schema for a message."""
    id: Optional[int] = None
    session_id: str
    role: str
    avatar: Optional[str] = None
    content: str
    message_index: int = 0
    created_at: Optional[datetime] = None


class InterviewFeedbackRead(SQLModel):
    """Public read schema for feedback."""
    id: Optional[int] = None
    session_id: str
    feedback: str
    overall_score: Optional[int] = None
    created_at: Optional[datetime] = None


class InterviewQuestionScoreRead(SQLModel):
    """Public read schema for a question score."""
    id: Optional[int] = None
    session_id: str
    question_index: int = 0
    avatar: str = ""
    question_text: str = ""
    answer_text: str = ""
    score: float = 0.0
    ai_feedback: str = ""
    created_at: Optional[datetime] = None


class InterviewSessionDetail(InterviewSessionRead):
    """Session with messages, feedback, and question scores included."""
    messages: List[InterviewMessageRead] = []
    feedbacks: List[InterviewFeedbackRead] = []
    question_scores: List[InterviewQuestionScoreRead] = []
