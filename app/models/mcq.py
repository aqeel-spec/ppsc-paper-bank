from enum import Enum
from typing import Optional, List
from sqlmodel import SQLModel, Field

class AnswerOption(str, Enum):
    OPTION_A = "option_a"
    OPTION_B = "option_b"
    OPTION_C = "option_c"
    OPTION_D = "option_d"

class Category(str, Enum):
    ENGLISH = "english"
    MATHEMATICS = "mathematics"
    GENERAL_KNOWLEDGE = "general_knowledge"
    PAKISTAN_STUDIES = "pakistan_studies"
    COMPUTER_SCIENCE = "computer_science"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    ISLAMIC_STUDIES = "islamic_studies"
    CURRENT_AFFAIRS = "current_affairs"

class MCQBase(SQLModel):
    question_text: str = Field(index=True)
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: AnswerOption
    category: Category = Field(index=True)

class MCQ(MCQBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

class MCQCreate(MCQBase):
    pass

class MCQUpdate(SQLModel):
    question_text: Optional[str] = None
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    correct_answer: Optional[AnswerOption] = None

class MCQBulkCreate(SQLModel):
    mcqs: List[MCQCreate]
