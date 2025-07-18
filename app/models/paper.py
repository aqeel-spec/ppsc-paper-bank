from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from sqlmodel import SQLModel, Field, Relationship
from pydantic import BaseModel

if TYPE_CHECKING:
    from .mcqs_bank import MCQ


from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import JSON
from pydantic import BaseModel

if TYPE_CHECKING:
    from .mcqs_bank import MCQ


class PaperModel(SQLModel, table=True):
    __tablename__ = "paper"

    id: Optional[int] = Field(default=None, primary_key=True)
    website_id: Optional[int] = Field(foreign_key="website.web_id", index=True)
    title: Optional[str] = None
    paper_url: Optional[str] = None
    year: Optional[int] = None
    paper_type: Optional[str] = None
    mcq_links: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    difficulty: Optional[str] = None
    tags: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

    # Relationships
    paper_mcqs: List["PaperMCQ"] = Relationship(back_populates="paper")


class PaperMCQ(SQLModel, table=True):
    __tablename__ = "paper_mcq"

    paper_id: int = Field(foreign_key="paper.id", primary_key=True)
    mcq_id: int = Field(foreign_key="mcqs_bank.id", primary_key=True)

    paper: PaperModel = Relationship(back_populates="paper_mcqs")
    mcq: "MCQ" = Relationship()


class PaperCreate(SQLModel):
    website_id: Optional[int] = None
    title: Optional[str] = None
    paper_url: Optional[str] = None
    year: Optional[int] = None
    paper_type: Optional[str] = None
    mcq_links: Optional[dict] = None
    difficulty: Optional[str] = None
    tags: Optional[str] = None


class PaperUpdate(SQLModel):
    website_id: Optional[int] = None
    title: Optional[str] = None
    paper_url: Optional[str] = None
    year: Optional[int] = None
    paper_type: Optional[str] = None
    mcq_links: Optional[dict] = None
    difficulty: Optional[str] = None
    tags: Optional[str] = None


class PaperResponse(BaseModel):
    id: int
    website_id: Optional[int] = None
    title: Optional[str] = None
    paper_url: Optional[str] = None
    year: Optional[int] = None
    paper_type: Optional[str] = None
    mcq_links: Optional[dict] = None
    difficulty: Optional[str] = None
    tags: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    mcqs: List["MCQ"] = []  # or use a lighter MCQRead schema if preferred

    class Config:
        from_attributes = True
