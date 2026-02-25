"""
app/models/suggestion.py — User suggestion and upvote models.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, Index, String, Text
from sqlmodel import Field, SQLModel


class SuggestionCategory(str, Enum):
    ui = "ui"
    content = "content"
    feature = "feature"
    bug = "bug"
    other = "other"


class SuggestionStatus(str, Enum):
    pending = "pending"
    reviewed = "reviewed"
    accepted = "accepted"
    rejected = "rejected"


class UserSuggestion(SQLModel, table=True):
    __tablename__ = "user_suggestions"

    id: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String(36), primary_key=True))
    user_id: Optional[str] = Field(default=None, sa_column=Column(String(36)))  # nullable = anonymous
    title: str = Field(sa_column=Column(String(255), nullable=False))
    body: str = Field(sa_column=Column(Text, nullable=False))
    category: str = Field(default=SuggestionCategory.feature, sa_column=Column(String(20), default="feature"))
    status: str = Field(default=SuggestionStatus.pending, sa_column=Column(String(20), default="pending"))
    upvotes: int = Field(default=0)
    admin_reply: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SuggestionUpvote(SQLModel, table=True):
    __tablename__ = "suggestion_upvotes"
    __table_args__ = (
        Index("ix_suggestion_upvotes_unique", "suggestion_id", "user_id", unique=True),
    )

    id: int = Field(default=None, primary_key=True)
    suggestion_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    user_id: str = Field(sa_column=Column(String(36), nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Pydantic schemas
class SuggestionCreate(SQLModel):
    title: str
    body: str
    category: str = SuggestionCategory.feature


class SuggestionRead(SQLModel):
    id: str
    user_id: Optional[str]
    title: str
    body: str
    category: str
    status: str
    upvotes: int
    admin_reply: Optional[str]
    created_at: datetime


class SuggestionAdminUpdate(SQLModel):
    status: Optional[str] = None
    admin_reply: Optional[str] = None
