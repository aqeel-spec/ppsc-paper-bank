from typing import Optional, List, Dict
from datetime import datetime

from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import DateTime
from sqlalchemy.sql import func
from pydantic import BaseModel, model_validator 
from enum import Enum


class CategorySlug(str, Enum):
    ppsc_all_mcqs_2025 = "ppsc_all_mcqs_2025"
    urdu                = "urdu"
    english             = "english"
    computer            = "computer"
    geography           = "geography"

class AnswerOption(str, Enum):
    OPTION_A = "option_a"
    OPTION_B = "option_b"
    OPTION_C = "option_c"
    OPTION_D = "option_d"


class Category(SQLModel, table=True):
    __tablename__ = "category"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(
        index=True,
        unique=True,
        description="machine‐safe key, e.g. 'ppsc_all_mcqs_2025'"
    )
    name: str = Field(
        description="human‐readable, e.g. 'PPSC All MCQs 2025'"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime,
            server_default=func.now(),
            nullable=False
        ),
        description="when this category was first created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime,
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        ),
        description="last time this category record was modified"
    )

    mcqs: List["MCQ"] = Relationship(back_populates="category")


class MCQBase(SQLModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: AnswerOption
    explanation: Optional[str] = None


class MCQ(MCQBase, table=True):
    __tablename__ = "mcq"

    id: Optional[int] = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="category.id", index=True)
    category: Category = Relationship(back_populates="mcqs")
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
    question_text:  str
    option_a:       str
    option_b:       str
    option_c:       str
    option_d:       str
    correct_answer: AnswerOption
    explanation:    Optional[str] = None

    # client will supply exactly one of these:
    category_slug:     Optional[str] = Field(
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
        slug     = values.get("category_slug")
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


class PaperModel(SQLModel, table=True):
    __tablename__ = "paper"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    mcq_links: List["PaperMCQ"] = Relationship(back_populates="paper")


class PaperMCQ(SQLModel, table=True):
    __tablename__ = "paper_mcq"

    paper_id: int = Field(foreign_key="paper.id", primary_key=True)
    mcq_id: int = Field(foreign_key="mcq.id", primary_key=True)

    paper: PaperModel = Relationship(back_populates="mcq_links")
    mcq: MCQ = Relationship()


class PaperResponse(BaseModel):
    id: int
    created_at: datetime
    mcqs: List[MCQ]  # or use a lighter MCQRead schema if preferred

    class Config:
        orm_mode = True



# from enum import Enum
# from typing import Optional, List
# from sqlmodel import SQLModel, Field, Relationship
# from datetime import datetime 
# from pydantic import BaseModel

# class AnswerOption(str, Enum):
#     OPTION_A = "option_a"
#     OPTION_B = "option_b"
#     OPTION_C = "option_c"
#     OPTION_D = "option_d"

# class Category(str, Enum):
#     PPSC_PAST_PAPERS = "ppsc_past_papers"      # ← generic bucket
#     PPSC_ALL_2025    = "ppsc_all_mcqs_2025"
#     PPSC_ALL_2024    = "ppsc_all_mcqs_2024"    # ← year‐specific
#     URDU          = "urdu"
#     ENGLISH       = "english"
#     COMPUTER      = "computer"
#     GEOGRAPHY     = "geography"
#     ISLAMIC       = "islamic_study"
#     PAKISTAN      = "pakistan_study"
#     CURRENT       = "current_affairs"
#     EVERYDAY      = "everyday_science"
#     BASIC_MATH    = "basic_mathematics"
#     GENERAL_KNOW  = "gk_general_knowledge"

# class MCQBase(SQLModel):
#     question_text: str = Field(index=True)
#     option_a: str
#     option_b: str
#     option_c: str
#     option_d: str
#     correct_answer: AnswerOption
#     explanation: Optional[str] = None               # ← new!
#     category: Category = Field(index=True)

# class MCQ(MCQBase, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     created_at: datetime = Field(default=datetime.now())
#     updated_at: Optional[datetime] = Field(default=datetime.now())

# class MCQCreate(MCQBase):
#     pass

# class MCQUpdate(SQLModel):
#     question_text: Optional[str] = None
#     option_a: Optional[str] = None
#     option_b: Optional[str] = None
#     option_c: Optional[str] = None
#     option_d: Optional[str] = None
#     explanation: Optional[str]= None  # ← new!
#     correct_answer: Optional[AnswerOption] = None
#     category: Optional[Category] = None  # you can also allow updating category

# class MCQBulkCreate(SQLModel):
#     mcqs: List[MCQCreate]

# # --- New DB tables (add these to models.py and migrate) ---
# class PaperModel(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     created_at: datetime = Field(default_factory=datetime.now())
#     mcq_links: List["PaperMCQ"] = Relationship(back_populates="paper")

# class PaperMCQ(SQLModel, table=True):
#     paper_id: int = Field(foreign_key="papermodel.id", primary_key=True)
#     mcq_id: int = Field(foreign_key="mcq.id", primary_key=True)
#     paper: PaperModel     = Relationship(back_populates="mcq_links")
#     mcq: MCQ        = Relationship()
    

# # --- Response schemas ---
# class PaperResponse(BaseModel):
#     id: int
#     created_at: datetime
#     mcqs: List[MCQ]
