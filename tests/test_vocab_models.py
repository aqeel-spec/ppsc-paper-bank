from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app.models.vocab import (
    BOX_INTERVAL_DAYS,
    BOX_LEVEL_LABELS,
    BUILTIN_CARD_THEMES,
    VOCAB_METHODS,
    DayPlan,
    UserVocabSettings,
    VocabCustomTheme,
    VocabDailyProgress,
    Word,
)


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


def test_box_intervals_match_product_rules():
    assert BOX_INTERVAL_DAYS == {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}
    assert BOX_LEVEL_LABELS[1] == "daily"
    assert BOX_LEVEL_LABELS[5] == "30 days (mastered)"


def test_vocab_methods_and_themes_contract():
    method_keys = {item["key"] for item in VOCAB_METHODS}
    assert "american_flashcard" in method_keys
    assert len(VOCAB_METHODS) == 6

    assert len(BUILTIN_CARD_THEMES) == 11
    assert BUILTIN_CARD_THEMES[0]["key"] == "default_classic"
    assert BUILTIN_CARD_THEMES[0]["is_default"] is True


def test_vocab_settings_theme_progress_models_create():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        settings = UserVocabSettings(user_id="user-1")
        session.add(settings)

        theme = VocabCustomTheme(user_id="user-1", name="My Theme", theme_config="{\"bg\":\"#fff\"}")
        session.add(theme)

        progress = VocabDailyProgress(
            user_id="user-1",
            progress_date=date.today(),
            words_added=5,
            reviews_done=10,
            correct_reviews=8,
            wrong_reviews=2,
            avg_recall_seconds=9,
            retention_rate=80.0,
            pace_score=3.0,
        )
        session.add(progress)
        session.commit()

        assert settings.cards_per_day == 5
        assert settings.selected_method == "american_flashcard"
        assert settings.selected_theme == "default_classic"
        assert theme.name == "My Theme"
        assert progress.words_added == 5
        assert progress.retention_rate == 80.0
