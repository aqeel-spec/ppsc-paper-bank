from datetime import date, datetime, timezone
from typing import Optional, List, Any, Dict
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text, func
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NewsArticle(SQLModel, table=True):
    __tablename__ = "news_articles"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True, index=True),
    )
    source: str = Field(sa_column=Column(String(50), nullable=False, index=True))  # "dawn", "thenews"
    section: str = Field(sa_column=Column(String(50), nullable=False, index=True))  # "front-page", "opinion", "world", "business", "pakistan", etc.
    title: str = Field(sa_column=Column(String(500), nullable=False, index=True))
    url: str = Field(sa_column=Column(String(1000), nullable=False, unique=True, index=True))
    image_url: Optional[str] = Field(default=None, sa_column=Column(String(1000), nullable=True))
    audio_url: Optional[str] = Field(default=None, sa_column=Column(String(1000), nullable=True))
    audio_cues_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))  # Serialized JSON of AudioSyncCue[]
    published_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    scraped_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    author: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    body_text: str = Field(sa_column=Column(Text, nullable=False))
    summary: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(default="fresh", sa_column=Column(String(50), nullable=False, default="fresh"))  # "fresh", "stale", "needs_review"
    is_current_affairs: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True, index=True))
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class NewsMCQ(SQLModel, table=True):
    __tablename__ = "news_mcqs"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True, index=True),
    )
    article_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(36), nullable=True, index=True),
    )
    question: str = Field(sa_column=Column(Text, nullable=False))
    option_1: str = Field(sa_column=Column(String(500), nullable=False))
    option_2: str = Field(sa_column=Column(String(500), nullable=False))
    option_3: str = Field(sa_column=Column(String(500), nullable=False))
    option_4: str = Field(sa_column=Column(String(500), nullable=False))
    correct_index: int = Field(default=0, sa_column=Column(Integer, nullable=False))  # 0 to 3
    correct_answer: str = Field(sa_column=Column(String(500), nullable=False))
    explanation: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    category: str = Field(default="Current Affairs", sa_column=Column(String(100), nullable=False, index=True))
    difficulty: str = Field(default="medium", sa_column=Column(String(50), nullable=False, default="medium"))
    target_date: date = Field(
        default_factory=lambda: _utc_now().date(),
        sa_column=Column(Date, nullable=False, index=True),
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class NewsVocab(SQLModel, table=True):
    __tablename__ = "news_vocabs"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True, index=True),
    )
    article_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(36), nullable=True, index=True),
    )
    word: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    phonetic: Optional[str] = Field(default=None, sa_column=Column(String(100), nullable=True))
    part_of_speech: Optional[str] = Field(default=None, sa_column=Column(String(50), nullable=True))
    css_meaning: str = Field(sa_column=Column(Text, nullable=False))
    synonyms: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    antonyms: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    context_in_article: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    css_usage_example: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    target_date: date = Field(
        default_factory=lambda: _utc_now().date(),
        sa_column=Column(Date, nullable=False, index=True),
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class NewsPoVAnalysis(SQLModel, table=True):
    __tablename__ = "news_pov_analyses"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True, index=True),
    )
    article_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    article_title: str = Field(sa_column=Column(String(500), nullable=False))
    author: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    theme: str = Field(sa_column=Column(String(255), nullable=False))
    relevant_papers_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    central_thesis: str = Field(sa_column=Column(Text, nullable=False))
    key_arguments_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    policy_recommendations_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


# ─── Pydantic Transfer Schemas ───────────────────────────────────────────────

class NewsArticleRead(SQLModel):
    id: str
    source: str
    section: str
    title: str
    url: str
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    audio_cues_json: Optional[str] = None
    published_at: datetime
    updated_at: Optional[datetime] = None
    scraped_at: datetime
    author: Optional[str] = None
    body_text: str
    summary: Optional[str] = None
    status: str
    is_current_affairs: bool
    created_at: datetime


class NewsMCQRead(SQLModel):
    id: str
    article_id: Optional[str] = None
    question: str
    option_1: str
    option_2: str
    option_3: str
    option_4: str
    correct_index: int
    correct_answer: str
    explanation: Optional[str] = None
    category: str
    difficulty: str
    target_date: date
    created_at: datetime


class NewsVocabRead(SQLModel):
    id: str
    article_id: Optional[str] = None
    word: str
    phonetic: Optional[str] = None
    part_of_speech: Optional[str] = None
    css_meaning: str
    synonyms: Optional[str] = None
    antonyms: Optional[str] = None
    context_in_article: Optional[str] = None
    css_usage_example: Optional[str] = None
    target_date: date
    created_at: datetime


class NewsPoVAnalysisRead(SQLModel):
    id: str
    article_id: str
    article_title: str
    author: Optional[str] = None
    theme: str
    relevant_papers_json: Optional[str] = None
    central_thesis: str
    key_arguments_json: Optional[str] = None
    policy_recommendations_json: Optional[str] = None
    created_at: datetime


class NewsCollectionRequest(SQLModel):
    source: str = "all"  # "all", "dawn", "thenews"
    section: str = "opinion"  # "all", "opinion", "front-page", "pakistan", "world", "business", "latest-news"
    date_str: Optional[str] = None  # "YYYY-MM-DD"
    limit: int = 10
    include_audio: bool = True
    include_chunks: bool = True
    include_images: bool = True


class NewsCollectionResponse(SQLModel):
    success: bool
    date: str
    total_saved: int
    total_fetched: int
    articles: List[NewsArticleRead]
    error: Optional[str] = None


class NewsVocabImportRequest(SQLModel):
    vocab_ids: List[str]
    box: int = 1
    tags: Optional[str] = "Current Affairs, Newspaper"


class NewsAgentChatRequest(SQLModel):
    message: str
    article_id: Optional[str] = None
    session_id: Optional[str] = None
    date_str: Optional[str] = None
