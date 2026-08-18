from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlmodel import Field, SQLModel


class SubjectPreparationNote(SQLModel, table=True):
    __tablename__ = "subject_preparation_notes"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True),
    )
    title: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    subject: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    format: str = Field(default="md", sa_column=Column(String(20), nullable=False, index=True))
    summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    file_name: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    file_url: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    content_markdown: Optional[str] = Field(default=None, sa_column=Column(Text))
    content_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_visible: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False, index=True))
    created_by: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))


class SubjectPreparationNoteCreate(SQLModel):
    title: str
    subject: str
    format: str = "md"
    summary: Optional[str] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    content_markdown: Optional[str] = None
    content_text: Optional[str] = None
    is_visible: bool = False


class SubjectPreparationNoteUpdate(SQLModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    format: Optional[str] = None
    summary: Optional[str] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    content_markdown: Optional[str] = None
    content_text: Optional[str] = None
    is_visible: Optional[bool] = None


class SubjectPreparationNoteRead(SQLModel):
    id: str
    title: str
    subject: str
    format: str
    summary: Optional[str] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    content_markdown: Optional[str] = None
    content_text: Optional[str] = None
    is_visible: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
