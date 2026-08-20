"""
News & Current Affairs API Routes
Exposes newspaper ingestion, daily MCQs, academic vocabulary, PoV analysis, and AI news assistant.
"""
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from sqlmodel import Session, select, func, desc

from app.database import get_session
from app.security import get_current_user, get_optional_user
from app.models.user import User
from app.models.news import (
    NewsArticle,
    NewsMCQ,
    NewsVocab,
    NewsPoVAnalysis,
    NewsArticleRead,
    NewsMCQRead,
    NewsVocabRead,
    NewsPoVAnalysisRead,
    NewsCollectionRequest,
    NewsCollectionResponse,
    NewsVocabImportRequest,
    NewsAgentChatRequest,
)
from app.models.vocab import WordRead
from app.services.news_service import NewsService
from ppsc_agents.agent_system import (
    get_current_model,
    SESSION_DB,
    search_internet,
    search_web_deep,
)
from agents import Agent, Runner, SQLiteSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/news", tags=["News & Current Affairs"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/nav")
def get_news_navigation():
    """Returns header navigation payload for Daily News & Current Affairs."""
    return {
        "title": "Daily News & Current Affairs",
        "name": "News",
        "url": "/news",
        "badge": "Daily",
        "sections": [
            {"name": "All News", "slug": "all"},
            {"name": "Opinion & Editorial", "slug": "opinion"},
            {"name": "Pakistan / National", "slug": "pakistan"},
            {"name": "World / Geopolitics", "slug": "world"},
            {"name": "Economy & Business", "slug": "business"},
            {"name": "Front Page", "slug": "front-page"},
            {"name": "Latest Breaking", "slug": "latest-news"},
        ],
    }


@router.get("/stats")
def get_news_stats(db: Session = Depends(get_session)):
    """Retrieve overall statistics for news articles, MCQs, and vocabulary."""
    total_articles = db.exec(select(func.count(NewsArticle.id))).one()
    total_mcqs = db.exec(select(func.count(NewsMCQ.id))).one()
    total_vocab = db.exec(select(func.count(NewsVocab.id))).one()
    total_pov = db.exec(select(func.count(NewsPoVAnalysis.id))).one()

    today = date.today()
    today_articles = db.exec(
        select(func.count(NewsArticle.id)).where(
            func.date(NewsArticle.published_at) == today
        )
    ).one()

    # Section counts
    sections_query = db.exec(
        select(NewsArticle.section, func.count(NewsArticle.id))
        .group_by(NewsArticle.section)
    ).all()
    section_breakdown = {s: count for s, count in sections_query}

    return {
        "total_articles": total_articles,
        "today_articles": today_articles,
        "total_mcqs": total_mcqs,
        "total_vocab": total_vocab,
        "total_pov_analyses": total_pov,
        "section_breakdown": section_breakdown,
    }


@router.get("/collect", response_model=NewsCollectionResponse)
async def trigger_news_collection_get(
    source: str = Query(default="all", description="dawn, thenews, or all"),
    section: str = Query(default="opinion", description="opinion, front-page, pakistan, world, business, latest-news, or all"),
    date_str: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    limit: int = Query(default=10, ge=1, le=100),
    include_audio: bool = Query(default=True),
    include_chunks: bool = Query(default=True),
    include_images: bool = Query(default=True),
    db: Session = Depends(get_session),
):
    """
    Trigger newspaper acquisition via GET (browser friendly) from NEW_API_URL.
    """
    result = await NewsService.fetch_and_save_articles(
        db=db,
        source=source,
        section=section,
        date_str=date_str,
        limit=limit,
        include_audio=include_audio,
        include_chunks=include_chunks,
        include_images=include_images,
    )
    return NewsCollectionResponse(
        success=result["success"],
        date=result["date"],
        total_saved=result["total_saved"],
        total_fetched=result["total_fetched"],
        articles=result["articles"],
        error=result.get("error"),
    )


@router.post("/collect", response_model=NewsCollectionResponse)
async def trigger_news_collection(
    payload: NewsCollectionRequest = NewsCollectionRequest(),
    db: Session = Depends(get_session),
):
    """
    Trigger newspaper acquisition from NEW_API_URL (Dawn & The News)
    and store normalized articles in the database.
    """
    result = await NewsService.fetch_and_save_articles(
        db=db,
        source=payload.source,
        section=payload.section,
        date_str=payload.date_str,
        limit=payload.limit,
        include_audio=payload.include_audio,
        include_chunks=payload.include_chunks,
        include_images=payload.include_images,
    )
    return NewsCollectionResponse(
        success=result["success"],
        date=result["date"],
        total_saved=result["total_saved"],
        total_fetched=result["total_fetched"],
        articles=result["articles"],
        error=result.get("error"),
    )


@router.get("/articles", response_model=List[NewsArticleRead])
def list_news_articles(
    source: Optional[str] = Query(default=None, description="Filter by source: dawn, thenews"),
    section: Optional[str] = Query(default=None, description="Filter by section: opinion, world, etc."),
    date_str: Optional[str] = Query(default=None, description="Filter by date (YYYY-MM-DD)"),
    search: Optional[str] = Query(default=None, description="Search keyword in title or body"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_session),
):
    """List news articles with filters and pagination."""
    query = select(NewsArticle)

    if source and source != "all":
        query = query.where(NewsArticle.source == source)
    if section and section != "all":
        query = query.where(NewsArticle.section == section)
    if date_str:
        try:
            target_d = date.fromisoformat(date_str)
            query = query.where(func.date(NewsArticle.published_at) == target_d)
        except Exception:
            pass
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            (NewsArticle.title.ilike(term)) | (NewsArticle.body_text.ilike(term))
        )

    query = query.order_by(desc(NewsArticle.published_at), desc(NewsArticle.created_at)).offset(offset).limit(limit)
    return db.exec(query).all()


@router.get("/articles/{article_id}", response_model=Dict[str, Any])
def get_single_news_article(
    article_id: str,
    db: Session = Depends(get_session),
):
    """Retrieve full article detail including audio cues, linked MCQs, Vocab, and PoV analysis."""
    article = db.get(NewsArticle, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    mcqs = db.exec(select(NewsMCQ).where(NewsMCQ.article_id == article.id)).all()
    vocabs = db.exec(select(NewsVocab).where(NewsVocab.article_id == article.id)).all()
    pov = db.exec(select(NewsPoVAnalysis).where(NewsPoVAnalysis.article_id == article.id)).first()

    audio_cues = []
    if article.audio_cues_json:
        try:
            audio_cues = json.loads(article.audio_cues_json)
        except Exception:
            pass

    return {
        "article": article,
        "audio_cues": audio_cues,
        "mcqs": mcqs,
        "vocabs": vocabs,
        "pov_analysis": pov,
    }


@router.get("/articles/{article_id}/ai-summary")
@router.post("/articles/{article_id}/ai-summary")
async def generate_article_summary(
    article_id: str,
    db: Session = Depends(get_session),
):
    """Generate an AI summary for a specific news article."""
    try:
        summary = await NewsService.generate_article_summary(article_id, db)
        return {"article_id": article_id, "summary": summary}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")


@router.get("/articles/{article_id}/ai-mcqs", response_model=List[NewsMCQRead])
@router.post("/articles/{article_id}/ai-mcqs", response_model=List[NewsMCQRead])
async def generate_article_mcqs(
    article_id: str,
    count: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_session),
):
    """Generate exam-grade factual MCQs for a news article using AI."""
    try:
        mcqs = await NewsService.generate_article_mcqs(article_id, count, db)
        return mcqs
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate MCQs: {str(e)}")


@router.get("/articles/{article_id}/ai-vocab", response_model=List[NewsVocabRead])
@router.post("/articles/{article_id}/ai-vocab", response_model=List[NewsVocabRead])
async def generate_article_vocab(
    article_id: str,
    count: int = Query(default=4, ge=1, le=10),
    db: Session = Depends(get_session),
):
    """Extract high-register CSS/PPSC vocabulary from an article using AI."""
    try:
        vocabs = await NewsService.generate_article_vocab(article_id, count, db)
        return vocabs
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate vocab: {str(e)}")


@router.get("/articles/{article_id}/ai-pov", response_model=NewsPoVAnalysisRead)
@router.post("/articles/{article_id}/ai-pov", response_model=NewsPoVAnalysisRead)
async def generate_article_pov(
    article_id: str,
    db: Session = Depends(get_session),
):
    """Generate a structured Point-of-View policy analysis from an opinion/editorial article."""
    try:
        pov = await NewsService.generate_article_pov(article_id, db)
        return pov
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PoV analysis: {str(e)}")


@router.get("/mcqs", response_model=List[NewsMCQRead])
def list_news_mcqs(
    date_str: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    category: Optional[str] = Query(default=None),
    article_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_session),
):
    """List daily news MCQs."""
    query = select(NewsMCQ)
    if date_str:
        try:
            target_d = date.fromisoformat(date_str)
            query = query.where(NewsMCQ.target_date == target_d)
        except Exception:
            pass
    if category and category != "all":
        query = query.where(NewsMCQ.category == category)
    if article_id:
        query = query.where(NewsMCQ.article_id == article_id)

    query = query.order_by(desc(NewsMCQ.created_at)).limit(limit)
    return db.exec(query).all()


@router.get("/vocab", response_model=List[NewsVocabRead])
def list_news_vocab(
    date_str: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    word: Optional[str] = Query(default=None),
    article_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_session),
):
    """List extracted academic vocabulary from newspapers."""
    query = select(NewsVocab)
    if date_str:
        try:
            target_d = date.fromisoformat(date_str)
            query = query.where(NewsVocab.target_date == target_d)
        except Exception:
            pass
    if word and word.strip():
        query = query.where(NewsVocab.word.ilike(f"%{word.strip()}%"))
    if article_id:
        query = query.where(NewsVocab.article_id == article_id)

    query = query.order_by(desc(NewsVocab.created_at)).limit(limit)
    return db.exec(query).all()


@router.post("/vocab/import-to-deck", response_model=List[WordRead])
def import_news_vocab_to_deck(
    payload: NewsVocabImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Import extracted news vocabulary words directly into the user's personal Leitner study box."""
    if not payload.vocab_ids:
        raise HTTPException(status_code=400, detail="vocab_ids cannot be empty")

    imported = NewsService.import_vocab_to_user_deck(
        user_id=str(current_user.id),
        vocab_ids=payload.vocab_ids,
        box=payload.box,
        tags=payload.tags,
        db=db,
    )
    return imported


@router.post("/ai/chat")
async def news_ai_chat(
    payload: NewsAgentChatRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_session),
):
    """
    Conversational AI mentor for news, current affairs analysis, and exam Q&A.
    """
    user_msg = payload.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="message is required")

    # Fetch context
    context_lines = []
    if payload.article_id:
        art = db.get(NewsArticle, payload.article_id)
        if art:
            context_lines.append(f"Active Article Title: {art.title}")
            context_lines.append(f"Author: {art.author or 'Staff'}, Source: {art.source.upper()}")
            context_lines.append(f"Content Excerpt:\n{art.body_text[:2500]}")
    else:
        # Provide sample of today's news
        today = date.today()
        recent_arts = db.exec(
            select(NewsArticle).order_by(desc(NewsArticle.published_at)).limit(5)
        ).all()
        if recent_arts:
            context_lines.append("Today's Top News Headlines:")
            for a in recent_arts:
                context_lines.append(f"- [{a.source.upper()}] {a.title} ({a.section})")

    context_str = "\n".join(context_lines)

    instructions = (
        "You are the PPSC/CSS Senior Current Affairs & Editorial AI Mentor.\n"
        "Your role is to assist candidates with in-depth understanding of daily newspaper stories, "
        "geopolitical developments, constitutional matters, economic trends, and exam preparations.\n"
        f"Context:\n{context_str}\n\n"
        "Guidelines:\n"
        "1. Give structured, objective, and intellectually rigorous answers suitable for CSS/PPSC papers.\n"
        "2. When discussing issues, highlight facts, constitutional provisions, economic data, and balanced perspectives.\n"
        "3. If asked for latest statistics, external updates, or background context not present in the article, use search_web_deep or search_internet to fetch live data.\n"
        "4. If asked for MCQs, vocab, or mnemonics, format them clearly."
    )

    model = get_current_model()
    agent = Agent(
        name="News Current Affairs Agent",
        instructions=instructions,
        model=model,
        tools=[search_internet, search_web_deep],
    )

    user_id_str = str(current_user.id) if current_user else "anonymous_guest"
    session_id = payload.session_id or f"news_chat_{user_id_str}"
    memory_session = SQLiteSession(session_id, SESSION_DB)

    result = await Runner.run(agent, user_msg, session=memory_session)

    return {
        "reply": result.final_output,
        "session_id": session_id,
    }
