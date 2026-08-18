from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text, func
from sqlmodel import UniqueConstraint, Field, SQLModel


BOX_INTERVAL_DAYS = {
    1: 1,
    2: 3,
    3: 7,
    4: 14,
    5: 30,
}

BOX_LEVEL_LABELS = {
    1: "daily",
    2: "3 days",
    3: "7 days",
    4: "14 days",
    5: "30 days (mastered)",
}


VOCAB_METHODS = [
    {
        "key": "american_flashcard",
        "label": "American Flashcard Method (default)",
        "description": "Standard prompt on front and meaning/example on back.",
    },
    {
        "key": "leitner_box",
        "label": "Leitner Box Method",
        "description": "Spaced repetition by box progression and review intervals.",
    },
    {
        "key": "active_recall",
        "label": "Active Recall",
        "description": "Answer from memory before seeing hints.",
    },
    {
        "key": "context_sentence",
        "label": "Context Sentence Method",
        "description": "Focus on usage in contextual examples.",
    },
    {
        "key": "synonym_antonym_chain",
        "label": "Synonym/Antonym Chain",
        "description": "Link words by similar and opposite meanings.",
    },
    {
        "key": "mnemonic_hook",
        "label": "Mnemonic Hook",
        "description": "Attach visual or sound hooks for long-term recall.",
    },
]


BUILTIN_CARD_THEMES = [
    {"key": "default_classic", "name": "Default Classic", "is_default": True},
    {"key": "ocean_blue", "name": "Ocean Blue", "is_default": False},
    {"key": "forest_green", "name": "Forest Green", "is_default": False},
    {"key": "sunrise_orange", "name": "Sunrise Orange", "is_default": False},
    {"key": "charcoal_slate", "name": "Charcoal Slate", "is_default": False},
    {"key": "sandstone", "name": "Sandstone", "is_default": False},
    {"key": "mint_fresh", "name": "Mint Fresh", "is_default": False},
    {"key": "ruby_focus", "name": "Ruby Focus", "is_default": False},
    {"key": "sky_light", "name": "Sky Light", "is_default": False},
    {"key": "lavender_gray", "name": "Lavender Gray", "is_default": False},
    {"key": "mono_minimal", "name": "Mono Minimal", "is_default": False},
]


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
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_day_plans_user_date"),)

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True),
    )
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    plan_date: date = Field(
        default_factory=date.today,
        sa_column=Column("date", Date, nullable=False, index=True),
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


class UserVocabSettings(SQLModel, table=True):
    __tablename__ = "user_vocab_settings"

    user_id: str = Field(sa_column=Column(String(36), primary_key=True))
    cards_per_day: int = Field(default=5, sa_column=Column(Integer, nullable=False, default=5))
    selected_method: str = Field(
        default="american_flashcard",
        sa_column=Column(String(80), nullable=False, default="american_flashcard"),
    )
    selected_theme: str = Field(
        default="default_classic",
        sa_column=Column(String(80), nullable=False, default="default_classic"),
    )
    custom_card_fields: Optional[str] = Field(default=None, sa_column=Column(Text))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class VocabCustomTheme(SQLModel, table=True):
    __tablename__ = "vocab_custom_themes"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True),
    )
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    name: str = Field(sa_column=Column(String(120), nullable=False))
    theme_config: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class VocabDailyProgress(SQLModel, table=True):
    __tablename__ = "vocab_daily_progress"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(String(36), primary_key=True),
    )
    user_id: str = Field(sa_column=Column(String(36), nullable=False, index=True))
    progress_date: date = Field(sa_column=Column(Date, nullable=False, index=True))
    words_added: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    reviews_done: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    correct_reviews: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    wrong_reviews: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    avg_recall_seconds: Optional[int] = Field(default=None, sa_column=Column(Integer))
    retention_rate: Optional[float] = Field(default=None, sa_column=Column(Float))
    pace_score: Optional[float] = Field(default=None, sa_column=Column(Float))
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


class UserVocabSettingsUpdate(SQLModel):
    cards_per_day: Optional[int] = None
    selected_method: Optional[str] = None
    selected_theme: Optional[str] = None
    custom_card_fields: Optional[str] = None
    notes: Optional[str] = None


class UserVocabSettingsRead(SQLModel):
    user_id: str
    cards_per_day: int
    selected_method: str
    selected_theme: str
    custom_card_fields: Optional[str] = None
    notes: Optional[str] = None
    updated_at: datetime


class VocabCustomThemeCreate(SQLModel):
    name: str
    theme_config: Optional[str] = None


class VocabCustomThemeRead(SQLModel):
    id: str
    user_id: str
    name: str
    theme_config: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class VocabDailyProgressSync(SQLModel):
    progress_date: Optional[date] = None
    words_added: int = 0
    reviews_done: int = 0
    correct_reviews: int = 0
    wrong_reviews: int = 0
    avg_recall_seconds: Optional[int] = None


class VocabDailyProgressRead(SQLModel):
    id: str
    user_id: str
    progress_date: date
    words_added: int
    reviews_done: int
    correct_reviews: int
    wrong_reviews: int
    avg_recall_seconds: Optional[int] = None
    retention_rate: Optional[float] = None
    pace_score: Optional[float] = None
    due_reminder_sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class VocabAiExplanation(SQLModel, table=True):
    __tablename__ = "vocab_ai_explanations"

    id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True, index=True),
    )
    user_id: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    card_id: Optional[str] = Field(default=None, sa_column=Column(String(100), nullable=True, index=True))
    word: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    user_prompt: str = Field(sa_column=Column(Text, nullable=False))
    ai_response: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class VocabAiExplanationCreate(SQLModel):
    card_id: Optional[str] = None
    word: str
    user_prompt: str
    ai_response: str


class VocabAiExplanationRead(SQLModel):
    id: int
    user_id: str
    card_id: Optional[str] = None
    word: str
    user_prompt: str
    ai_response: str
    created_at: datetime


class VocabQuizResult(SQLModel, table=True):
    __tablename__ = "vocab_quiz_results"

    id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True, index=True),
    )
    user_id: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    total_questions: int = Field(default=0, sa_column=Column(Integer, default=0, nullable=False))
    correct_count: int = Field(default=0, sa_column=Column(Integer, default=0, nullable=False))
    accuracy: float = Field(default=0.0, sa_column=Column(Float, default=0.0, nullable=False))
    voice_used: bool = Field(default=False, sa_column=Column(Boolean, default=False, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class VocabQuizResultCreate(SQLModel):
    total_questions: int
    correct_count: int
    accuracy: float
    voice_used: bool = False


class VocabQuizResultRead(SQLModel):
    id: int
    user_id: str
    total_questions: int
    correct_count: int
    accuracy: float
    voice_used: bool
    created_at: datetime
