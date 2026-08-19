"""
Automated Test Suite for Daily News & Current Affairs Acquisition and AI Services
"""
import pytest
from datetime import date, datetime, timezone
import json
from unittest.mock import patch, AsyncMock

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from fastapi.testclient import TestClient

from app.models.news import (
    NewsArticle,
    NewsMCQ,
    NewsVocab,
    NewsPoVAnalysis,
)
from app.models.top_bar import TopBar
from app.models.vocab import Word
from app.models.user import User
from app.security import get_current_user
from app.services.news_service import NewsService
from app.database import get_session
from main import app


@pytest.fixture(name="sqlite_session")
def sqlite_session_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_news_models_crud(sqlite_session: Session):
    # 1. Create Article
    article = NewsArticle(
        source="dawn",
        section="opinion",
        title="Pakistan Economy in 2026",
        url="https://www.dawn.com/news/1234567",
        body_text="Pakistan is negotiating a new economic framework with multilateral lenders.",
        author="Khurram Husain",
        audio_url="https://i.dawn.com/tts/1234567.mp3",
        audio_cues_json=json.dumps([{"id": 1, "text": "Pakistan", "start_ms": 0, "end_ms": 500}]),
        published_at=datetime.now(timezone.utc),
        is_current_affairs=True,
    )
    sqlite_session.add(article)
    sqlite_session.commit()
    sqlite_session.refresh(article)

    assert article.id is not None
    assert article.source == "dawn"
    assert article.is_current_affairs is True

    # 2. Create Linked MCQ
    mcq = NewsMCQ(
        article_id=article.id,
        question="Which international financial institution is assisting Pakistan?",
        option_1="IMF",
        option_2="World Bank",
        option_3="ADB",
        option_4="AIIB",
        correct_index=0,
        correct_answer="IMF",
        category="Economy & Business",
        target_date=date.today(),
    )
    sqlite_session.add(mcq)
    sqlite_session.commit()
    sqlite_session.refresh(mcq)

    assert mcq.id is not None
    assert mcq.correct_answer == "IMF"
    assert mcq.article_id == article.id

    # 3. Create Linked Vocab
    vocab = NewsVocab(
        article_id=article.id,
        word="fiscal",
        phonetic="/ˈfɪskəl/",
        part_of_speech="adjective",
        css_meaning="Relating to government revenue, especially taxes.",
        synonyms="monetary, financial, budgetary",
        context_in_article="Strict fiscal consolidation is required.",
        css_usage_example="The government must enforce strict fiscal discipline.",
        target_date=date.today(),
    )
    sqlite_session.add(vocab)
    sqlite_session.commit()
    sqlite_session.refresh(vocab)

    assert vocab.id is not None
    assert vocab.word == "fiscal"

    # 4. Test Vocab Import to User Deck
    user_id = "test_user_uuid_123"
    imported = NewsService.import_vocab_to_user_deck(
        user_id=user_id,
        vocab_ids=[vocab.id],
        box=1,
        tags="Current Affairs",
        db=sqlite_session,
    )
    assert len(imported) == 1
    assert imported[0].word == "fiscal"
    assert imported[0].user_id == user_id


def test_topbar_seed(sqlite_session: Session):
    NewsService.ensure_topbar_entry(sqlite_session)
    topbar = sqlite_session.exec(select(TopBar).where(TopBar.name == "News")).first()
    assert topbar is not None
    assert topbar.url == "/news"


def test_api_news_navigation_and_stats(sqlite_session: Session):
    def get_session_override():
        yield sqlite_session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)

    try:
        nav_res = client.get("/api/news/nav")
        assert nav_res.status_code == 200
        nav_data = nav_res.json()
        assert nav_data["name"] == "News"
        assert nav_data["url"] == "/news"

        stats_res = client.get("/api/news/stats")
        assert stats_res.status_code == 200
        stats_data = stats_res.json()
        assert "total_articles" in stats_data
        assert "total_mcqs" in stats_data
        assert "total_vocab" in stats_data
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_api_news_articles_and_filters(sqlite_session: Session):
    def get_session_override():
        yield sqlite_session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)

    try:
        # Seed 2 articles
        art1 = NewsArticle(
            source="dawn",
            section="opinion",
            title="Foreign Policy and Multipolarity",
            url="https://www.dawn.com/news/opinion-1",
            body_text="Diplomatic relations with regional neighbors are evolving rapidly.",
            author="Zahid Hussain",
            published_at=datetime.now(timezone.utc),
            audio_url="https://i.dawn.com/tts/op1.mp3",
            audio_cues_json=json.dumps([{"id": 1, "text": "Diplomatic", "start_ms": 0, "end_ms": 600}]),
        )
        art2 = NewsArticle(
            source="thenews",
            section="world",
            title="UN Security Council Resolves Middle East Crisis",
            url="https://www.thenews.com.pk/world/un-sc-1",
            body_text="The United Nations passed a landmark resolution today.",
            author="Staff Reporter",
            published_at=datetime.now(timezone.utc),
        )
        sqlite_session.add(art1)
        sqlite_session.add(art2)
        sqlite_session.commit()
        sqlite_session.refresh(art1)
        sqlite_session.refresh(art2)

        # 1. Filter by source
        res_dawn = client.get("/api/news/articles?source=dawn")
        assert res_dawn.status_code == 200
        assert len(res_dawn.json()) == 1
        assert res_dawn.json()[0]["source"] == "dawn"

        # 2. Filter by section
        res_world = client.get("/api/news/articles?section=world")
        assert res_world.status_code == 200
        assert len(res_world.json()) == 1
        assert res_world.json()[0]["section"] == "world"

        # 3. Search query
        res_search = client.get("/api/news/articles?search=multipolarity")
        assert res_search.status_code == 200
        assert len(res_search.json()) == 1
        assert "Foreign Policy" in res_search.json()[0]["title"]

        # 4. Detail endpoint
        res_detail = client.get(f"/api/news/articles/{art1.id}")
        assert res_detail.status_code == 200
        detail_data = res_detail.json()
        assert detail_data["article"]["id"] == art1.id
        assert len(detail_data["audio_cues"]) == 1
        assert detail_data["audio_cues"][0]["text"] == "Diplomatic"

    finally:
        app.dependency_overrides.pop(get_session, None)


def test_api_mcqs_and_vocab_queries(sqlite_session: Session):
    def get_session_override():
        yield sqlite_session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)

    try:
        today_val = date.today()
        # Seed MCQ
        mcq = NewsMCQ(
            question="Who is the Chief Justice of Pakistan in 2026?",
            option_1="Justice Yahya Afridi",
            option_2="Justice Mansoor Ali Shah",
            option_3="Justice Munib Akhtar",
            option_4="Justice Ayesha Malik",
            correct_index=0,
            correct_answer="Justice Yahya Afridi",
            category="Judiciary",
            target_date=today_val,
        )
        # Seed Vocab
        vocab = NewsVocab(
            word="intransigence",
            phonetic="/ɪnˈtrænsɪdʒəns/",
            part_of_speech="noun",
            css_meaning="Refusal to change one's views or to agree about something.",
            synonyms="stubbornness, inflexibility",
            target_date=today_val,
        )
        sqlite_session.add(mcq)
        sqlite_session.add(vocab)
        sqlite_session.commit()

        # Query MCQs
        mcqs_res = client.get(f"/api/news/mcqs?date_str={today_val.isoformat()}")
        assert mcqs_res.status_code == 200
        assert len(mcqs_res.json()) >= 1
        assert mcqs_res.json()[0]["question"] == "Who is the Chief Justice of Pakistan in 2026?"

        # Query Vocab
        vocab_res = client.get(f"/api/news/vocab?word=intransigence")
        assert vocab_res.status_code == 200
        assert len(vocab_res.json()) == 1
        assert vocab_res.json()[0]["word"] == "intransigence"

    finally:
        app.dependency_overrides.pop(get_session, None)


def test_vocab_deck_import_api(sqlite_session: Session):
    def get_session_override():
        yield sqlite_session

    mock_user = User(
        id="user_deck_tester_999",
        username="decktester",
        email="decktester@example.com",
        password_hash="fake_hash",
        is_active=True,
    )
    sqlite_session.add(mock_user)
    sqlite_session.commit()

    def get_user_override():
        return mock_user

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = get_user_override
    client = TestClient(app)

    try:
        vocab = NewsVocab(
            word="parsimonious",
            phonetic="/ˌpɑː.sɪˈməʊ.ni.əs/",
            part_of_speech="adjective",
            css_meaning="Unwilling to spend money or use resources; frugal.",
            target_date=date.today(),
        )
        sqlite_session.add(vocab)
        sqlite_session.commit()
        sqlite_session.refresh(vocab)

        payload = {
            "vocab_ids": [vocab.id],
            "box": 1,
            "tags": "Current Affairs, Editorials",
        }
        res = client.post("/api/news/vocab/import-to-deck", json=payload)
        assert res.status_code == 200
        imported_list = res.json()
        assert len(imported_list) == 1
        assert imported_list[0]["word"] == "parsimonious"
        assert imported_list[0]["user_id"] == "user_deck_tester_999"
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_news_service_fetch_mock(sqlite_session: Session):
    mock_payload = {
        "success": True,
        "date": "2026-08-19",
        "total": 1,
        "articles": [
            {
                "source": "dawn",
                "section": "opinion",
                "title": "Mock Ingested Article",
                "url": "https://www.dawn.com/news/mock-1",
                "image_url": "https://i.dawn.com/mock.jpg",
                "audio_url": "https://i.dawn.com/mock.mp3",
                "audio_cues": [{"id": 1, "text": "Mock", "start_ms": 0, "end_ms": 400}],
                "published_at": "2026-08-19T04:40:34Z",
                "author": "Editorial Board",
                "body_text": "This is mock article content extracted by the Flow API pipeline.",
                "status": "fresh",
            }
        ],
    }

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: mock_payload

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        result = await NewsService.fetch_and_save_articles(
            db=sqlite_session,
            source="dawn",
            section="opinion",
            date_str="2026-08-19",
            limit=5,
        )
        assert result["success"] is True
        assert result["total_saved"] == 1
        saved_art = sqlite_session.exec(select(NewsArticle).where(NewsArticle.url == "https://www.dawn.com/news/mock-1")).first()
        assert saved_art is not None
        assert saved_art.title == "Mock Ingested Article"
        assert saved_art.audio_url == "https://i.dawn.com/mock.mp3"
