from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from enum import Enum

from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import DateTime, Text
from sqlalchemy.sql import func
from pydantic import BaseModel, model_validator

if TYPE_CHECKING:
    from .category import Category


class AnswerOption(str, Enum):
    OPTION_A = "option_a"
    OPTION_B = "option_b"
    OPTION_C = "option_c"
    OPTION_D = "option_d"


class MCQBase(SQLModel):
    question_text: str = Field(sa_column=Column(Text))
    option_a: str = Field(sa_column=Column(Text))
    option_b: str = Field(sa_column=Column(Text))
    option_c: str = Field(sa_column=Column(Text))
    option_d: str = Field(sa_column=Column(Text))
    correct_answer: AnswerOption
    explanation: Optional[str] = Field(default=None, sa_column=Column(Text))
    ai_explanation: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="Cached AI-generated explanation (saved to avoid repeat token usage)",
    )


class MCQ(MCQBase, table=True):
    __tablename__ = "mcqs_bank"

    id: Optional[int] = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="category.id", index=True)
    category: "Category" = Relationship(back_populates="mcqs")
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime,
            server_default=func.now(),
            nullable=False
        )
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime,
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        )
    )


class MCQCreate(SQLModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: AnswerOption
    explanation: Optional[str] = None

    # client will supply exactly one of these:
    category_slug: Optional[str] = Field(
        None, description="Pick one slug from GET /categories"
    )
    new_category_slug: Optional[str] = Field(
        None, description="Only if creating a brand-new category"
    )
    new_category_name: Optional[str] = Field(
        None, description="Only if creating a brand-new category"
    )

    @model_validator(mode="before")
    def _validate_one_or_other(cls, values):
        slug = values.get("category_slug")
        new_slug = values.get("new_category_slug")
        new_name = values.get("new_category_name")
        if slug and (new_slug or new_name):
            raise ValueError("Use either `category_slug` OR `new_category_*`, not both.")
        if not slug and not (new_slug and new_name):
            raise ValueError("Either pick `category_slug` or supply both `new_category_slug` + `new_category_name`.")
        return values


class MCQUpdate(SQLModel):
    question_text: Optional[str] = None
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    correct_answer: Optional[AnswerOption] = None
    explanation: Optional[str] = None
    category_slug: Optional[str] = None


class MCQBulkCreate(SQLModel):
    mcqs: List[MCQCreate]


class MCQRead(SQLModel):
    id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: AnswerOption
    explanation: Optional[str] = None
    ai_explanation: Optional[str] = None
    category_id: int
    created_at: datetime
    updated_at: datetime
