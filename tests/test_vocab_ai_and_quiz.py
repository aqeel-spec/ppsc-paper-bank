import pytest
from datetime import datetime, timezone
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

from app.models.vocab import (
    VocabAiExplanation,
    VocabAiExplanationCreate,
    VocabAiExplanationRead,
    VocabQuizResult,
    VocabQuizResultCreate,
    VocabQuizResultRead,
)


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_vocab_ai_explanation_persistence(test_db: Session):
    explanation = VocabAiExplanation(
        user_id="user_123",
        card_id="card_456",
        word="Abundant",
        user_prompt="Explain this word with an exam context.",
        ai_response="Abundant means existing or available in large quantities; plentiful.",
    )
    test_db.add(explanation)
    test_db.commit()
    test_db.refresh(explanation)

    assert explanation.id is not None
    assert explanation.user_id == "user_123"
    assert explanation.word == "Abundant"

    fetched = test_db.exec(
        select(VocabAiExplanation).where(VocabAiExplanation.user_id == "user_123")
    ).all()
    assert len(fetched) == 1
    assert fetched[0].card_id == "card_456"
    assert fetched[0].ai_response.startswith("Abundant")


def test_vocab_quiz_result_persistence(test_db: Session):
    quiz = VocabQuizResult(
        user_id="user_123",
        total_questions=10,
        correct_count=8,
        accuracy=80.0,
        voice_used=True,
    )
    test_db.add(quiz)
    test_db.commit()
    test_db.refresh(quiz)

    assert quiz.id is not None
    assert quiz.user_id == "user_123"
    assert quiz.total_questions == 10
    assert quiz.correct_count == 8
    assert quiz.accuracy == 80.0
    assert quiz.voice_used is True

    fetched = test_db.exec(
        select(VocabQuizResult).where(VocabQuizResult.user_id == "user_123")
    ).all()
    assert len(fetched) == 1
    assert fetched[0].accuracy == 80.0
