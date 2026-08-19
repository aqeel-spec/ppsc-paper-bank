"""
Newspaper & Current Affairs Acquisition and AI Knowledge Service
Integrates with NEW_API_URL (Flow API / Newspaper Scraper) and LLMs (Bedrock/GitHub).
"""
import os
import json
import logging
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any
from uuid import uuid4

import httpx
from sqlmodel import Session, select, func, desc

from app.models.news import (
    NewsArticle,
    NewsMCQ,
    NewsVocab,
    NewsPoVAnalysis,
    NewsArticleRead,
)
from app.models.vocab import Word
from app.models.top_bar import TopBar
from ppsc_agents.api_key_rotator import get_llm_config
from agents import Agent, Runner, SQLiteSession
from ppsc_agents.agent_system import get_current_model, SESSION_DB

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_new_api_url() -> str:
    url = os.getenv("NEW_API_URL", "http://localhost:5000").strip()
    return url.rstrip("/")


def _parse_iso_datetime(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val
    if not val:
        return _utc_now()
    try:
        clean = str(val).replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return _utc_now()


class NewsService:
    @staticmethod
    def ensure_topbar_entry(db: Session) -> None:
        """Ensure News item is registered in TopBar navigation."""
        try:
            existing = db.exec(
                select(TopBar).where(
                    (TopBar.name == "News") | (TopBar.url == "/news") | (TopBar.url == "/views/news") | (TopBar.title == "Daily News")
                )
            ).first()
            if not existing:
                news_topbar = TopBar(
                    title="Daily News & Current Affairs",
                    name="News",
                    url="/news",
                )
                db.add(news_topbar)
                db.commit()
                logger.info("Added 'Daily News & Current Affairs' to TopBar navigation.")
        except Exception as e:
            logger.warning(f"Could not auto-seed News TopBar: {e}")

    @staticmethod
    async def fetch_and_save_articles(
        db: Session,
        source: str = "all",
        section: str = "opinion",
        date_str: Optional[str] = None,
        limit: int = 10,
        include_audio: bool = True,
        include_chunks: bool = True,
        include_images: bool = True,
        full_body: bool = True,
    ) -> Dict[str, Any]:
        """
        Fetch normalized articles from NEW_API_URL and upsert them in the database.
        """
        base_url = _get_new_api_url()
        endpoint = f"{base_url}/api/newspapers"
        
        params: Dict[str, Any] = {
            "source": source,
            "section": section,
            "limit": limit,
            "include_audio": str(include_audio).lower(),
            "include_chunks": str(include_chunks).lower(),
            "include_images": str(include_images).lower(),
            "full_body": str(full_body).lower(),
        }
        if date_str:
            params["date"] = date_str

        logger.info(f"Querying Newspaper API at {endpoint} with params: {params}")

        articles_data = []
        api_date = date_str or date.today().isoformat()
        api_error = None

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(endpoint, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    articles_data = data.get("articles", [])
                    api_date = data.get("date", api_date)
                else:
                    api_error = f"API returned status {resp.status_code}: {resp.text[:300]}"
                    logger.warning(api_error)
        except Exception as e:
            api_error = f"Failed to connect to NEW_API_URL ({endpoint}): {str(e)}"
            logger.error(api_error)

        saved_articles: List[NewsArticle] = []

        for item in articles_data:
            url = item.get("url")
            if not url:
                continue

            existing = db.exec(select(NewsArticle).where(NewsArticle.url == url)).first()

            audio_cues = item.get("audio_cues")
            audio_cues_json = json.dumps(audio_cues) if audio_cues else None
            pub_at = _parse_iso_datetime(item.get("published_at"))
            upd_at = _parse_iso_datetime(item.get("updated_at")) if item.get("updated_at") else None
            scr_at = _parse_iso_datetime(item.get("scraped_at"))

            is_ca = item.get("section", "").lower() in {
                "opinion", "editorial", "front-page", "national", "pakistan", "world", "business", "latest-news"
            }

            if existing:
                existing.title = item.get("title", existing.title)
                existing.source = item.get("source", existing.source)
                existing.section = item.get("section", existing.section)
                existing.body_text = item.get("body_text", existing.body_text)
                if item.get("image_url"):
                    existing.image_url = item.get("image_url")
                if item.get("audio_url"):
                    existing.audio_url = item.get("audio_url")
                if audio_cues_json:
                    existing.audio_cues_json = audio_cues_json
                existing.author = item.get("author", existing.author)
                existing.published_at = pub_at
                existing.updated_at = upd_at
                existing.scraped_at = scr_at
                existing.status = item.get("status", existing.status)
                existing.is_current_affairs = is_ca
                db.add(existing)
                saved_articles.append(existing)
            else:
                new_art = NewsArticle(
                    source=item.get("source", "dawn"),
                    section=item.get("section", section),
                    title=item.get("title", "Untitled Article"),
                    url=url,
                    image_url=item.get("image_url"),
                    audio_url=item.get("audio_url"),
                    audio_cues_json=audio_cues_json,
                    published_at=pub_at,
                    updated_at=upd_at,
                    scraped_at=scr_at,
                    author=item.get("author"),
                    body_text=item.get("body_text", ""),
                    status=item.get("status", "fresh"),
                    is_current_affairs=is_ca,
                )
                db.add(new_art)
                saved_articles.append(new_art)

        db.commit()
        for art in saved_articles:
            db.refresh(art)

        NewsService.ensure_topbar_entry(db)

        return {
            "success": api_error is None,
            "date": api_date,
            "total_saved": len(saved_articles),
            "total_fetched": len(articles_data),
            "articles": saved_articles,
            "error": api_error,
        }

    @staticmethod
    async def generate_article_summary(article_id: str, db: Session) -> str:
        """Use LLM to generate an exam-focused summary for an article."""
        article = db.get(NewsArticle, article_id)
        if not article:
            raise ValueError("Article not found")

        prompt = (
            f"You are a Senior CSS/PPSC Exam Mentor. Provide a high-yield summary of this news article for competitive exams:\n\n"
            f"Title: {article.title}\n"
            f"Author: {article.author or 'Staff'}\n"
            f"Source/Section: {article.source.upper()} - {article.section}\n\n"
            f"Article Content:\n{article.body_text[:4000]}\n\n"
            f"Structure your response strictly in Markdown:\n"
            f"### 📌 Core Synopsis\n"
            f"2 concise sentences explaining what happened and why it matters.\n\n"
            f"### 🔑 Key Exam Takeaways (Bullet Points)\n"
            f"- 3 to 4 analytical points highlighting facts, institutional roles, legal provisions, or economic impact.\n\n"
            f"### 🎯 Competitive Exam Angles\n"
            f"Mention which papers this relates to (e.g. Current Affairs, Pakistan Affairs, Essay) and how to quote it."
        )

        model = get_current_model()
        agent = Agent(name="News Summary Agent", instructions=prompt, model=model)
        result = await Runner.run(agent, "Generate summary now.")
        summary_text = result.final_output

        article.summary = summary_text
        db.add(article)
        db.commit()
        db.refresh(article)
        return summary_text

    @staticmethod
    async def generate_article_mcqs(
        article_id: str,
        count: int = 3,
        db: Session = None,
    ) -> List[NewsMCQ]:
        """Extract factual, exam-grade MCQs from a news article."""
        article = db.get(NewsArticle, article_id)
        if not article:
            raise ValueError("Article not found")

        prompt = (
            f"You are an expert examiner creating MCQs for PPSC, FPSC, CSS, and General Knowledge competitive exams.\n"
            f"Read the following article and generate {count} factual, exam-grade multiple-choice questions.\n\n"
            f"Article Title: {article.title}\n"
            f"Content:\n{article.body_text[:4000]}\n\n"
            f"STRICT RULES:\n"
            f"1. Focus on concrete verifiable facts: names, appointments, treaties, articles of constitution, court rulings, economic figures, committee names, or geographic locations.\n"
            f"2. Each question MUST have exactly 4 distinct options.\n"
            f"3. Specify correct_index (0-indexed: 0 for option_1, 1 for option_2, etc.) and correct_answer string.\n"
            f"4. Provide a clear explanation referencing the article context.\n"
            f"5. Return ONLY a valid JSON object matching this schema, with no surrounding markdown or explanation outside the JSON:\n"
            f'{{"mcqs": [{{"question": "...", "options": ["opt1", "opt2", "opt3", "opt4"], "correct_index": 0, "explanation": "...", "category": "Pakistan Affairs", "difficulty": "medium"}}]}}'
        )

        model = get_current_model()
        agent = Agent(name="News MCQ Agent", instructions=prompt, model=model)
        result = await Runner.run(agent, "Generate MCQs in JSON format.")
        
        output_text = result.final_output.strip()
        # Clean any code fence markdown
        if output_text.startswith("```"):
            lines = output_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            output_text = "\n".join(lines).strip()

        saved_mcqs: List[NewsMCQ] = []
        try:
            parsed = json.loads(output_text)
            raw_list = parsed.get("mcqs", [])
            target_dt = article.published_at.date() if article.published_at else date.today()

            for item in raw_list:
                opts = item.get("options", [])
                if len(opts) < 4:
                    continue
                c_idx = int(item.get("correct_index", 0))
                c_ans = opts[c_idx] if 0 <= c_idx < len(opts) else opts[0]

                mcq = NewsMCQ(
                    article_id=article.id,
                    question=item.get("question", "Question"),
                    option_1=opts[0],
                    option_2=opts[1],
                    option_3=opts[2],
                    option_4=opts[3],
                    correct_index=c_idx,
                    correct_answer=c_ans,
                    explanation=item.get("explanation"),
                    category=item.get("category", "Current Affairs"),
                    difficulty=item.get("difficulty", "medium"),
                    target_date=target_dt,
                )
                db.add(mcq)
                saved_mcqs.append(mcq)

            db.commit()
            for m in saved_mcqs:
                db.refresh(m)
        except Exception as e:
            logger.error(f"Error parsing MCQ JSON: {e}\nRaw output: {output_text}")

        return saved_mcqs

    @staticmethod
    async def generate_article_vocab(
        article_id: str,
        count: int = 4,
        db: Session = None,
    ) -> List[NewsVocab]:
        """Extract high-register academic vocabulary from an article."""
        article = db.get(NewsArticle, article_id)
        if not article:
            raise ValueError("Article not found")

        prompt = (
            f"You are a CSS English Précis & Composition and Essay master tutor.\n"
            f"Extract {count} high-register, academic words and idiomatic expressions from this article that candidates should learn for CSS/PPSC.\n\n"
            f"Article Title: {article.title}\n"
            f"Content:\n{article.body_text[:4000]}\n\n"
            f"RULES:\n"
            f"1. Select academic, high-scoring words (e.g., lacuna, indictment, devolution, contrapuntal, disenfranchise, intransigence).\n"
            f"2. Provide accurate phonetic pronunciation, part of speech, CSS context definition, synonyms, antonyms, context in article, and an exam policy essay sentence.\n"
            f"3. Return ONLY a valid JSON object matching this schema with no extra text:\n"
            f'{{"vocab": [{{"word": "...", "phonetic": "/.../", "part_of_speech": "noun", "css_meaning": "...", "synonyms": ["..."], "antonyms": ["..."], "context_in_article": "...", "css_usage_example": "..."}}]}}'
        )

        model = get_current_model()
        agent = Agent(name="News Vocab Agent", instructions=prompt, model=model)
        result = await Runner.run(agent, "Generate vocab in JSON format.")
        
        output_text = result.final_output.strip()
        if output_text.startswith("```"):
            lines = output_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            output_text = "\n".join(lines).strip()

        saved_vocab: List[NewsVocab] = []
        try:
            parsed = json.loads(output_text)
            raw_list = parsed.get("vocab", [])
            target_dt = article.published_at.date() if article.published_at else date.today()

            for item in raw_list:
                word_text = item.get("word", "").strip()
                if not word_text:
                    continue

                syns = item.get("synonyms")
                if isinstance(syns, list):
                    syns = ", ".join(syns)
                ants = item.get("antonyms")
                if isinstance(ants, list):
                    ants = ", ".join(ants)

                vocab = NewsVocab(
                    article_id=article.id,
                    word=word_text,
                    phonetic=item.get("phonetic"),
                    part_of_speech=item.get("part_of_speech"),
                    css_meaning=item.get("css_meaning", "Contextual definition"),
                    synonyms=syns,
                    antonyms=ants,
                    context_in_article=item.get("context_in_article"),
                    css_usage_example=item.get("css_usage_example"),
                    target_date=target_dt,
                )
                db.add(vocab)
                saved_vocab.append(vocab)

            db.commit()
            for v in saved_vocab:
                db.refresh(v)
        except Exception as e:
            logger.error(f"Error parsing Vocab JSON: {e}\nRaw output: {output_text}")

        return saved_vocab

    @staticmethod
    async def generate_article_pov(article_id: str, db: Session) -> NewsPoVAnalysis:
        """Extract Point-of-View (PoV) policy analysis from opinion/editorial."""
        article = db.get(NewsArticle, article_id)
        if not article:
            raise ValueError("Article not found")

        prompt = (
            f"You are an expert CSS / PMS Foreign Policy and Governance analyst.\n"
            f"Distill this editorial/opinion article into a structured Point-of-View (PoV) outline for CSS Essay and Current Affairs papers.\n\n"
            f"Title: {article.title}\n"
            f"Author: {article.author or 'Editorial Board'}\n"
            f"Content:\n{article.body_text[:4000]}\n\n"
            f"RULES:\n"
            f"1. Identify the central thesis (the core argument of the author).\n"
            f"2. Provide 3-4 core structured arguments.\n"
            f"3. List actionable policy recommendations / way forward.\n"
            f"4. List relevant CSS syllabus papers.\n"
            f"5. Return ONLY a valid JSON object matching this schema:\n"
            f'{{"pov_analysis": {{"theme": "...", "relevant_papers": ["CSS Essay", "CSS Pakistan Affairs"], "central_thesis": "...", "key_arguments": ["...", "..."], "policy_recommendations": ["...", "..."]}}}}'
        )

        model = get_current_model()
        agent = Agent(name="News PoV Agent", instructions=prompt, model=model)
        result = await Runner.run(agent, "Generate PoV analysis in JSON.")

        output_text = result.final_output.strip()
        if output_text.startswith("```"):
            lines = output_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            output_text = "\n".join(lines).strip()

        parsed = json.loads(output_text).get("pov_analysis", {})
        papers = parsed.get("relevant_papers", [])
        args = parsed.get("key_arguments", [])
        recs = parsed.get("policy_recommendations", [])

        existing = db.exec(select(NewsPoVAnalysis).where(NewsPoVAnalysis.article_id == article.id)).first()
        if existing:
            existing.theme = parsed.get("theme", "Governance & Policy")
            existing.relevant_papers_json = json.dumps(papers)
            existing.central_thesis = parsed.get("central_thesis", "")
            existing.key_arguments_json = json.dumps(args)
            existing.policy_recommendations_json = json.dumps(recs)
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return existing
        else:
            pov = NewsPoVAnalysis(
                article_id=article.id,
                article_title=article.title,
                author=article.author,
                theme=parsed.get("theme", "Governance & Policy"),
                relevant_papers_json=json.dumps(papers),
                central_thesis=parsed.get("central_thesis", ""),
                key_arguments_json=json.dumps(args),
                policy_recommendations_json=json.dumps(recs),
            )
            db.add(pov)
            db.commit()
            db.refresh(pov)
            return pov

    @staticmethod
    def import_vocab_to_user_deck(
        user_id: str,
        vocab_ids: List[str],
        box: int = 1,
        tags: Optional[str] = "Current Affairs, Newspaper",
        db: Session = None,
    ) -> List[Word]:
        """Import extracted news vocab items directly into the user's Leitner study deck."""
        imported_words: List[Word] = []
        today = date.today()

        for vid in vocab_ids:
            nv = db.get(NewsVocab, vid)
            if not nv:
                continue

            # Check if user already has this word in their deck
            existing = db.exec(
                select(Word).where(
                    Word.user_id == user_id,
                    Word.word.ilike(nv.word.strip()),
                )
            ).first()

            if existing:
                continue

            word_obj = Word(
                user_id=user_id,
                word=nv.word.strip(),
                meaning=nv.css_meaning,
                relevant_meaning=nv.css_meaning,
                sentence=nv.css_usage_example or nv.context_in_article,
                hook=f"Phonetic: {nv.phonetic}" if nv.phonetic else None,
                synonyms=nv.synonyms,
                antonyms=nv.antonyms,
                tags=tags,
                box=box,
                scheduled_date=today,
                next_review=_utc_now(),
                completed=False,
            )
            db.add(word_obj)
            imported_words.append(word_obj)

        db.commit()
        for w in imported_words:
            db.refresh(w)

        return imported_words
