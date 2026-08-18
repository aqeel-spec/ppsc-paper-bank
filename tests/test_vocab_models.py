from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app.models.vocab import DayPlan, Word


def test_vocab_models_create_and_defaults():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        word = Word(
            user_id="user-1",
            word="abandon",
            meaning="to leave something behind",
            relevant_meaning="to stop supporting an idea",
            sentence="We must not abandon our goals.",
            hook="A boat can abandon the dock at dawn.",
            synonyms="leave, desert, forsake",
            antonyms="keep, continue, support",
            tags="essay, vocabulary, ppsc",
            scheduled_date=date.today(),
        )
        session.add(word)
        session.commit()
        session.refresh(word)

        plan = DayPlan(user_id="user-1", plan_date=date.today(), target_count=5)
        session.add(plan)
        session.commit()
        session.refresh(plan)

        assert word.box == 1
        assert word.completed is False
        assert word.next_review is not None
        assert word.revision_reminder_sent_at is None
        assert word.user_id == "user-1"
        assert word.relevant_meaning == "to stop supporting an idea"
        assert word.synonyms == "leave, desert, forsake"
        assert word.antonyms == "keep, continue, support"
        assert word.tags == "essay, vocabulary, ppsc"
        assert plan.target_count == 5
        assert plan.due_reminder_sent_at is None
        assert plan.user_id == "user-1"
