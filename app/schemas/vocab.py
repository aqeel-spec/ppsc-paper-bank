from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class VocabAiExplanationCreate(BaseModel):
    card_id: Optional[str] = None
    word: str
    user_prompt: str
    ai_response: str


class VocabAiExplanationRead(BaseModel):
    id: int
    user_id: str
    card_id: Optional[str] = None
    word: str
    user_prompt: str
    ai_response: str
    created_at: datetime

    class Config:
        from_attributes = True


class VocabQuizResultCreate(BaseModel):
    total_questions: int
    correct_count: int
    accuracy: float
    voice_used: bool = False


class VocabQuizResultRead(BaseModel):
    id: int
    user_id: str
    total_questions: int
    correct_count: int
    accuracy: float
    voice_used: bool
    created_at: datetime

    class Config:
        from_attributes = True
