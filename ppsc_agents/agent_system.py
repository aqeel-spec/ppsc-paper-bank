"""
Agent System for PPSC Paper Bank with Session Management
Uses OpenAI Agents SDK with GitHub Models (OpenAI-compatible endpoint)
Includes paper creation, session memory, and internet search
"""

import os
import asyncio
import httpx
import json
import contextvars
from typing import Optional, List
from datetime import datetime, date
from dotenv import load_dotenv
import logging

# Import from openai-agents package
import agents as openai_agents
from agents import Agent, Runner, function_tool, SQLiteSession
from agents.extensions.models.litellm_model import LitellmModel
from agents.models.interface import Model

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Suppress LiteLLM verbose output completely
import litellm
litellm.suppress_debug_info = True
litellm.set_verbose = False

# Also suppress LiteLLM's logger
litellm_logger = logging.getLogger('LiteLLM')
litellm_logger.setLevel(logging.ERROR)
litellm_logger.propagate = False

# Suppress OpenAI client retry logs
openai_logger = logging.getLogger('openai')
openai_logger.setLevel(logging.ERROR)
openai_logger.propagate = False

# Suppress httpx logs
httpx_logger = logging.getLogger('httpx')
httpx_logger.setLevel(logging.ERROR)
httpx_logger.propagate = False

# Suppress and disable OpenAI Agents telemetry / tracing export
try:
    from agents.tracing.setup import set_trace_provider
    from agents.tracing.provider import DefaultTraceProvider
    # Setting DefaultTraceProvider without backend exporter disables remote OpenAI trace export
    set_trace_provider(DefaultTraceProvider())
except Exception:
    pass

agents_logger = logging.getLogger('agents')
agents_logger.setLevel(logging.ERROR)
agents_logger.propagate = False

from .api_key_rotator import get_github_models_config, get_llm_config
from .offline_model import OfflineEchoModel
from types import SimpleNamespace


# Per-request auth header propagated from HTTP route into tool calls.
_CURRENT_AUTH_HEADER: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_auth_header",
    default=None,
)

# Fallback for tool execution environments where contextvars may not flow.
_GLOBAL_AUTH_HEADER: Optional[str] = None


def _auth_headers() -> dict:
    auth = _CURRENT_AUTH_HEADER.get() or _GLOBAL_AUTH_HEADER
    if auth:
        return {"Authorization": auth}
    return {}

# Optionally use application DB for LLM memory instead of SQLiteSession
USE_DB_MEMORY = os.getenv("USE_DB_MEMORY", "0").strip() in {"1", "true", "yes"}

if USE_DB_MEMORY:
    try:
        # Lazy import to avoid circular imports during startup
        from app.database import get_engine
        from app.models.interview import InterviewMessage, InterviewSession
        from sqlmodel import Session as SQLSession, select, col

        class DBSessionAdapter:
            """Adapter that satisfies the full SessionABC interface backed by the
            application's primary database (InterviewMessage table).

            The OpenAI Agents Runner requires four async methods:
              • get_items(limit)  – read history as SDK input-item dicts
              • add_items(items)  – persist new SDK items
              • pop_item()        – remove & return the most recent item
              • clear_session()   – wipe the session
            """

            def __init__(self, session_id: str):
                self.session_id = session_id

            @staticmethod
            def _default_avatar_for_memory() -> str:
                # InterviewSession.avatar is required; use a neutral value for agent chat memory sessions.
                return "agent"

            def _ensure_parent_session(self, db: SQLSession) -> None:
                existing = db.exec(
                    select(InterviewSession).where(InterviewSession.session_id == self.session_id)
                ).first()
                if existing is not None:
                    return

                db.add(
                    InterviewSession(
                        session_id=self.session_id,
                        avatar=self._default_avatar_for_memory(),
                        mode="single",
                        status="active",
                        total_messages=0,
                    )
                )
                db.commit()

            async def get_items(self, limit: int | None = None):
                """Return conversation history as SDK-compatible dicts."""
                try:
                    def _read():
                        with SQLSession(get_engine()) as db:
                            stmt = (
                                select(InterviewMessage)
                                .where(InterviewMessage.session_id == self.session_id)
                                .order_by(col(InterviewMessage.message_index))
                            )
                            if limit:
                                # Fetch the *latest* N rows in ascending order
                                total_stmt = select(InterviewMessage).where(
                                    InterviewMessage.session_id == self.session_id
                                )
                                all_rows = db.exec(total_stmt).all()
                                rows = sorted(all_rows, key=lambda r: r.message_index)
                                rows = rows[-limit:] if limit else rows
                            else:
                                rows = db.exec(stmt).all()
                            # Map custom DB roles → SDK roles (user/assistant/system only)
                            _ROLE_MAP = {
                                "candidate": "user",
                                "interviewer": "assistant",
                                "system": "system",
                                "user": "user",
                                "assistant": "assistant",
                            }
                            return [
                                {
                                    "role": _ROLE_MAP.get(r.role, "user"),
                                    "content": r.content,
                                }
                                for r in rows
                                if r.content  # skip empty-content rows
                            ]
                    import asyncio as _asyncio
                    return await _asyncio.to_thread(_read)
                except Exception:
                    return []

            async def add_items(self, items) -> None:
                """Persist new SDK items (list of dicts) to InterviewMessage table."""
                if not items:
                    return
                try:
                    import asyncio as _asyncio

                    def _write():
                        with SQLSession(get_engine()) as db:
                            self._ensure_parent_session(db)

                            # Determine next message_index
                            stmt = (
                                select(InterviewMessage)
                                .where(InterviewMessage.session_id == self.session_id)
                                .order_by(col(InterviewMessage.message_index).desc())
                            )
                            last = db.exec(stmt).first()
                            next_idx = (last.message_index + 1) if last else 0

                            for item in items:
                                role = item.get("role", "assistant") if isinstance(item, dict) else "assistant"
                                # content may be str or list[dict] — normalise to str
                                raw_content = item.get("content", "") if isinstance(item, dict) else str(item)
                                if isinstance(raw_content, list):
                                    # Extract text parts
                                    content = " ".join(
                                        part.get("text", "") if isinstance(part, dict) else str(part)
                                        for part in raw_content
                                    )
                                else:
                                    content = str(raw_content) if raw_content is not None else ""

                                msg = InterviewMessage(
                                    session_id=self.session_id,
                                    role=role,
                                    content=content,
                                    message_index=next_idx,
                                )
                                db.add(msg)
                                next_idx += 1

                            parent = db.exec(
                                select(InterviewSession).where(InterviewSession.session_id == self.session_id)
                            ).first()
                            if parent is not None:
                                parent.total_messages = next_idx
                                db.add(parent)
                            db.commit()

                    await _asyncio.to_thread(_write)
                except Exception as exc:
                    logger.warning(f"DBSessionAdapter.add_items failed: {exc}")

            async def pop_item(self):
                """Remove and return the most recent item, or None if empty."""
                try:
                    import asyncio as _asyncio

                    def _pop():
                        with SQLSession(get_engine()) as db:
                            stmt = (
                                select(InterviewMessage)
                                .where(InterviewMessage.session_id == self.session_id)
                                .order_by(col(InterviewMessage.message_index).desc())
                            )
                            row = db.exec(stmt).first()
                            if row is None:
                                return None
                            item = {"role": row.role, "content": row.content}
                            db.delete(row)
                            db.commit()
                            return item

                    return await _asyncio.to_thread(_pop)
                except Exception:
                    return None

            async def clear_session(self):
                """Delete all InterviewMessage rows for this session."""
                try:
                    import asyncio as _asyncio

                    def _clear():
                        with SQLSession(get_engine()) as db:
                            rows = db.exec(
                                select(InterviewMessage).where(
                                    InterviewMessage.session_id == self.session_id
                                )
                            ).all()
                            for row in rows:
                                db.delete(row)
                            db.commit()

                    await _asyncio.to_thread(_clear)
                except Exception:
                    pass

            def __repr__(self) -> str:  # pragma: no cover
                return f"DBSessionAdapter(session_id={self.session_id!r})"


    except Exception:
        USE_DB_MEMORY = False

# Load environment variables
load_dotenv()

# Offline mode (for running tests without external LLM quota)
OFFLINE_MODE = os.getenv("PPSC_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Session storage file
SESSION_DB = "agent_sessions.db"

# Initialize LLM configuration (AWS Bedrock Mantle with GitHub Models fallback)
_llm_config: dict[str, str] = get_github_models_config()

github_model: Model

if OFFLINE_MODE:
    logger.info("🧪 Offline mode enabled (PPSC_OFFLINE=1) — external LLM calls disabled")
    github_model = OfflineEchoModel()
else:
    token = _llm_config["api_key"]
    if not token:
        logger.warning(f"⚠️  {_llm_config['name']} API key is empty! Set it in .env.")

    logger.info(f"🔑 Using {_llm_config['name']}: {_llm_config['model']} @ {_llm_config['base_url']}")

    # Create LiteLLM model pointed at Bedrock Mantle or GitHub Models (OpenAI-compatible)
    github_model = LitellmModel(
        model=_llm_config["model"],
        api_key=_llm_config["api_key"],
        base_url=_llm_config["base_url"],
    )


def handle_api_error(error: Exception) -> bool:
    """
    Handle API errors. With a single provider there is no key rotation;
    returns False so callers surface the error immediately.
    """
    error_str = str(error)
    error_type = type(error).__name__
    logger.error(f"❌ API Error ({error_type}): {error_str[:150]}")
    return False


def get_current_model():
    """Get the current LLM model instance."""
    return github_model


def get_memory_session(session_id: Optional[str]):
    """Return a memory/session object appropriate for Runner.run.
    If `USE_DB_MEMORY` is enabled, return a `DBSessionAdapter` that reads from
    the main application DB. Otherwise return a `SQLiteSession` instance.
    If session_id is falsy, return None.
    """
    if not session_id:
        return None
    if USE_DB_MEMORY:
        try:
            return DBSessionAdapter(session_id)
        except Exception:
            return None
    # Fallback to lite sqlite session
    try:
        return SQLiteSession(session_id, SESSION_DB)
    except Exception:
        return None


# ------------------ Token estimation / logging ------------------
try:
    import tiktoken
    _tiktoken_available = True
except Exception:
    _tiktoken_available = False


def estimate_tokens(text: str, model_name: str | None = None) -> int:
    """Estimate token count for `text` using tiktoken if available,
    otherwise fall back to a simple heuristic (1 token ≈ 4 characters).
    """
    if not text:
        return 0
    if _tiktoken_available:
        try:
            enc = None
            if model_name:
                try:
                    enc = tiktoken.encoding_for_model(model_name)
                except Exception:
                    enc = tiktoken.get_encoding("gpt2")
            else:
                enc = tiktoken.get_encoding("gpt2")
            return len(enc.encode(text))
        except Exception:
            # fallback heuristic
            return max(1, int(len(text) / 4))
    # heuristic: average 4 chars per token
    return max(1, int(len(text) / 4))


def _deterministic_tool_failure_reply() -> str:
    return (
        "I could not complete that step because a required data/tool call failed. "
        "I will not ask unrelated category questions. "
        "Please resend your exact request in one line and I will retry directly. "
        "Example: 'Make me 2020 and 2021 plan, 5 papers/day, start 2026-04-20'."
    )


def _looks_like_tool_failure_output(text: str) -> bool:
    if not text:
        return True
    t = text.strip().lower()
    failure_markers = [
        "there was an error",
        "error while trying to fetch",
        "failed to fetch",
        "could you please specify what kind of mcqs",
        "which subject/category",
    ]
    return any(marker in t for marker in failure_markers)


# ==================== MCQ Agent Tools ====================

@function_tool
async def get_categories(limit: int = 100) -> str:
    """
    Get all available MCQ categories from the database with pagination.
    
    Args:
        limit: Maximum number of categories to retrieve (default: 100, max: 100)
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        params = {"limit": min(limit, 100), "offset": 0}
        response = await client.get(
            f"{API_BASE_URL}/categories/",
            params=params
        )
        data = response.json()
        
        if not data:
            return "No categories found."
        
        result = f"Available categories ({len(data)} shown):\n"
        for cat in data:
            result += f"- {cat.get('name', 'Unknown')} (slug: `{cat.get('slug', 'N/A')}`, ID: {cat.get('id', 'N/A')})\n"
        return result


@function_tool
async def get_category_mcqs(slug: str, explanation: bool = False, with_mcq: bool = True, limit: int = 5) -> str:
    """
    Get MCQs from a specific category with pagination.
    
    Args:
        slug: The category slug (e.g., 'computer-mcqs')
        explanation: Whether to include explanations
        with_mcq: Whether to include full MCQ details
        limit: Maximum number of MCQs to retrieve (default: 5, max: 20)
    """
    # Limit to reasonable maximum to avoid rate limits
    limit = min(limit, 20)
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        params = {
            "explanation": explanation,
            "with_mcq": with_mcq,
            "limit": limit,
            "offset": 0
        }
        response = await client.get(
            f"{API_BASE_URL}/categories/{slug}/with-mcqs",
            params=params
        )
        data = response.json()
        
        if not data or "mcqs" not in data:
            return f"No MCQs found for category '{slug}'."
        
        category_name = data.get("name", slug)
        total_mcqs = data.get("total_mcqs", 0)
        mcqs = data.get("mcqs", [])
        
        result = f"MCQs in category '{category_name}' ({len(mcqs)} shown, {total_mcqs} total):\n\n"
        for i, mcq in enumerate(mcqs, 1):
            result += f"{i}. {mcq.get('question_text', 'No question')}\n"
            result += f"   Answer: {mcq.get('correct_answer', 'N/A')}\n"
            if explanation and mcq.get('explanation'):
                result += f"   Explanation: {mcq.get('explanation')}\n"
            result += "\n"
        
        if total_mcqs > len(mcqs):
            result += f"... and {total_mcqs - len(mcqs)} more MCQs available\n"
        
        return result


@function_tool
async def get_single_mcq(mcq_id: int, explanation: bool = True) -> str:
    """
    Get a single MCQ by ID with full details.
    
    Args:
        mcq_id: The MCQ ID
        explanation: Whether to include explanation
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        params = {"explanation": explanation, "with_mcq": True}
        response = await client.get(
            f"{API_BASE_URL}/mcqs/with-mcqs/{mcq_id}",
            params=params
        )
        data = response.json()
        
        result = f"Question: {data.get('question_text', 'N/A')}\n\n"
        result += "Options:\n"
        for i in range(1, 6):
            opt = data.get(f"option_{i}")
            if opt:
                result += f"  {i}. {opt}\n"
        
        result += f"\nCorrect Answer: {data.get('correct_answer', 'N/A')}\n"
        
        if explanation and data.get('explanation'):
            result += f"\nExplanation: {data.get('explanation')}\n"
        
        return result


# ==================== Paper Agent Tools ====================

@function_tool
async def generate_paper(
    size: int = 100,
    difficulty: str = "medium",
    category_slug: Optional[str] = None,
    category_id: Optional[int] = None,
    year: Optional[int] = None,
    subject: Optional[str] = None,
    post: Optional[str] = None,
    min_repeats: Optional[int] = None,
    title: Optional[str] = None,
    paper_type: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    """
    Generate a single paper from MCQ bank criteria.
    This calls POST /papers/generate and should only be used when user explicitly asks
    for generating a paper. For yearwise mock series, use create_paper_series_from_years.
    """
    try:
        payload = {
            "size": max(1, min(size, 200)),
            "difficulty": difficulty or "medium",
            "category_slug": category_slug,
            "category_id": category_id,
            "year": year,
            "subject": subject,
            "post": post,
            "min_repeats": min_repeats,
            "title": title,
            "paper_type": paper_type,
            "tags": tags,
        }

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(
                f"{API_BASE_URL}/papers/generate",
                json=payload,
            )

            if response.status_code in (200, 201):
                data = response.json()
                mcqs = data.get("mcqs", [])
                return json.dumps({
                    "success": True,
                    "paper_id": data.get("id"),
                    "created_at": data.get("created_at"),
                    "category_id": data.get("category_id"),
                    "category_slug": data.get("category_slug"),
                    "question_count": len(mcqs),
                    "message": f"Generated paper with {len(mcqs)} MCQs.",
                }, indent=2)

            return json.dumps({
                "success": False,
                "status_code": response.status_code,
                "error": response.text,
            }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error generating paper: {str(e)}"
        }, indent=2)


@function_tool
async def create_paper_series_from_years(
    years: str,
    chunk_size: int = 5,
    start_date_iso: Optional[str] = None,
    title: Optional[str] = None,
    include_half_tests: bool = True,
    include_final_test: bool = True,
) -> str:
    """
    Create a paper series from existing papers by year.

    Args:
        years: Comma-separated years, e.g. "2020" or "2020,2021"
        chunk_size: Papers per day
        start_date_iso: Start date in YYYY-MM-DD (defaults to today)
        title: Optional custom series title
        include_half_tests: Include half tests at end
        include_final_test: Include final test at end
    """
    try:
        parsed_years = sorted({int(y.strip()) for y in years.split(",") if y.strip()})
        if not parsed_years:
            return json.dumps({
                "success": False,
                "error": "No valid years provided. Example: years='2020' or years='2020,2021'"
            }, indent=2)

        if start_date_iso:
            start_date = datetime.strptime(start_date_iso, "%Y-%m-%d").date().isoformat()
        else:
            start_date = date.today().isoformat()

        payload = {
            "title": title,
            "mode": "ai",
            "years": parsed_years,
            "chunk_size": max(1, min(chunk_size, 50)),
            "start_date": start_date,
            "include_half_tests": include_half_tests,
            "include_final_test": include_final_test,
        }

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(
                f"{API_BASE_URL}/paper-series",
                json=payload,
                headers=_auth_headers(),
            )

            if response.status_code in (200, 201):
                data = response.json()
                return json.dumps({
                    "success": True,
                    "series_id": data.get("id"),
                    "title": data.get("title"),
                    "years": data.get("years_json", parsed_years),
                    "chunk_size": data.get("chunk_size"),
                    "start_date": data.get("start_date"),
                    "end_date": data.get("end_date"),
                    "total_papers": data.get("total_papers"),
                    "status": data.get("status"),
                    "message": "Series created from existing paper bank by year.",
                }, indent=2)

            return json.dumps({
                "success": False,
                "status_code": response.status_code,
                "error": response.text,
            }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error creating paper series: {str(e)}"
        }, indent=2)


@function_tool
async def create_paper(
    title: str,
    difficulty: Optional[str] = None,
    category_slug: Optional[str] = None,
    question_count: int = 20,
    paper_type: str = "practice",
    year: Optional[int] = None,
) -> str:
    """
    Backward-compatible wrapper for older callers.

    Deprecated behavior:
    - This function now routes to /papers/generate via generate_paper.
    - For yearwise mock series, use create_paper_series_from_years.
    """
    try:
        payload = {
            "size": max(1, min(question_count, 200)),
            "difficulty": difficulty or "medium",
            "category_slug": category_slug,
            "year": year,
            "title": title,
            "paper_type": paper_type,
        }

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(
                f"{API_BASE_URL}/papers/generate",
                json=payload,
            )

            if response.status_code in (200, 201):
                data = response.json()
                mcqs = data.get("mcqs", [])
                return json.dumps({
                    "success": True,
                    "paper_id": data.get("id"),
                    "created_at": data.get("created_at"),
                    "question_count": len(mcqs),
                    "message": f"Generated paper with {len(mcqs)} MCQs.",
                }, indent=2)

            return json.dumps({
                "success": False,
                "status_code": response.status_code,
                "error": response.text,
            }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error creating paper: {str(e)}"
        }, indent=2)


@function_tool
async def get_papers(
    page: int = 1,
    per_page: int = 10
) -> str:
    """
    Get list of all available papers/tests with pagination.
    
    Args:
        page: Page number (default: 1)
        per_page: Number of papers per page (default: 10, max: 100)
    
    Returns:
        JSON string with list of papers and pagination metadata
    """
    try:
        # Match the API's pagination parameters
        params = {
            "page": page,
            "per_page": min(per_page, 100)  # Cap at 100
        }
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                f"{API_BASE_URL}/papers/",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                papers_dict = data.get("papers", {})
                
                # Convert papers dict to readable list
                papers_list = []
                for key, paper in papers_dict.items():
                    papers_list.append({
                        "id": key,
                        "length": paper.get("length"),
                        "created_at": paper.get("created_at"),
                        "view_url": paper.get("view_url"),
                        "pdf_with_answers": paper.get("pdf_a_url"),
                        "pdf_without_answers": paper.get("pdf_q_url")
                    })
                
                return json.dumps({
                    "success": True,
                    "total_papers": data.get("total_papers", 0),
                    "total_pages": data.get("total_pages", 0),
                    "current_page": data.get("page", 1),
                    "per_page": data.get("per_page", 10),
                    "papers": papers_list
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"Failed to fetch papers: {response.text}"
                })
    
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error fetching papers: {str(e)}"
        })


@function_tool
async def get_paper_mcqs(paper_id: int) -> str:
    """
    Get all MCQs from a specific paper.
    
    Args:
        paper_id: ID of the paper
    
    Returns:
        JSON string with paper details and all its MCQs
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                f"{API_BASE_URL}/papers/{paper_id}/mcqs"
            )
            
            if response.status_code == 200:
                data = response.json()
                return json.dumps({
                    "success": True,
                    "paper_id": paper_id,
                    "title": data.get("title"),
                    "question_count": len(data.get("mcqs", [])),
                    "mcqs": data.get("mcqs")
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"Paper not found or error: {response.text}"
                })
    
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error fetching paper MCQs: {str(e)}"
        })


@function_tool
async def search_internet(query: str, num_results: int = 5) -> str:
    """
    Search the internet for information about topics, MCQ questions, or exam preparation tips.
    
    Args:
        query: Search query string
        num_results: Number of results to return (default: 5)
    
    Returns:
        JSON string with search results
    """
    try:
        # Using DuckDuckGo instant answers API (no API key needed)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                # Get abstract/definition
                if data.get("AbstractText"):
                    results.append({
                        "title": data.get("Heading", "Definition"),
                        "snippet": data.get("AbstractText"),
                        "url": data.get("AbstractURL", "")
                    })
                
                # Get related topics
                for topic in data.get("RelatedTopics", [])[:num_results]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text", "").split(" - ")[0],
                            "snippet": topic.get("Text", ""),
                            "url": topic.get("FirstURL", "")
                        })
                
                return json.dumps({
                    "success": True,
                    "query": query,
                    "result_count": len(results),
                    "results": results[:num_results]
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": "Search failed"
                })
    
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Search error: {str(e)}"
        })


# ==================== Scraping Agent Tools ====================

@function_tool
async def start_scraping(
    website: str,
    url: str,
    slug: str,
    scrape_explanations: bool = False
) -> str:
    """
    Start scraping MCQs from a website.
    
    Args:
        website: Website name (testpoint, pakmcqs, or pacegkacademy)
        url: URL to scrape
        slug: Category slug to store MCQs
        scrape_explanations: Whether to scrape explanations
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.post(
            f"{API_BASE_URL}/scrape/start/",
            json={
                "website": website,
                "url": url,
                "slug": slug,
                "scrape_explanations": scrape_explanations
            }
        )
        data = response.json()
        return f"Scraping started: {data.get('message', 'Success')}"


# ==================== News & Current Affairs Agent Tools ====================

@function_tool
async def get_daily_news(section: str = "all", date_str: Optional[str] = None, limit: int = 5) -> str:
    """
    Fetch daily newspaper articles and current affairs headlines from Dawn and The News.

    Args:
        section: Section category (all, opinion, front-page, world, business, pakistan, latest-news)
        date_str: Optional target date in YYYY-MM-DD format
        limit: Maximum number of articles to return (default: 5)
    """
    try:
        params: dict = {"limit": min(limit, 10)}
        if section and section != "all":
            params["section"] = section
        if date_str:
            params["date_str"] = date_str

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(f"{API_BASE_URL}/api/news/articles", params=params)
            if response.status_code == 200:
                articles = response.json()
                if not articles:
                    return "No newspaper articles found for the given criteria."
                
                lines = [f"Found {len(articles)} news articles:\n"]
                for i, art in enumerate(articles, 1):
                    lines.append(f"{i}. [{art.get('source', '').upper()} - {art.get('section', '')}] {art.get('title', 'Untitled')}")
                    lines.append(f"   Published: {art.get('published_at', 'N/A')} | Author: {art.get('author') or 'Staff'}")
                    if art.get('summary'):
                        lines.append(f"   Summary: {art.get('summary')[:150]}...")
                    lines.append(f"   ID: {art.get('id')}\n")
                return "\n".join(lines)
            return f"Error fetching news: status code {response.status_code}"
    except Exception as e:
        return f"Error querying news articles: {str(e)}"


@function_tool
async def get_current_affairs_mcqs(date_str: Optional[str] = None, limit: int = 5) -> str:
    """
    Get daily news-based Current Affairs multiple-choice questions for PPSC/FPSC prep.

    Args:
        date_str: Optional date in YYYY-MM-DD
        limit: Number of questions (default: 5)
    """
    try:
        params: dict = {"limit": min(limit, 10)}
        if date_str:
            params["date_str"] = date_str

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(f"{API_BASE_URL}/api/news/mcqs", params=params)
            if response.status_code == 200:
                mcqs = response.json()
                if not mcqs:
                    return "No current affairs MCQs found."
                
                lines = [f"Daily Current Affairs MCQs ({len(mcqs)}):\n"]
                for i, m in enumerate(mcqs, 1):
                    lines.append(f"{i}. {m.get('question')}")
                    lines.append(f"   A) {m.get('option_1')}  B) {m.get('option_2')}  C) {m.get('option_3')}  D) {m.get('option_4')}")
                    lines.append(f"   Correct Answer: {m.get('correct_answer')}")
                    if m.get('explanation'):
                        lines.append(f"   Explanation: {m.get('explanation')}")
                    lines.append("")
                return "\n".join(lines)
            return f"Error fetching MCQs: {response.status_code}"
    except Exception as e:
        return f"Error retrieving current affairs MCQs: {str(e)}"


@function_tool
async def get_news_vocabulary(date_str: Optional[str] = None, limit: int = 5) -> str:
    """
    Get high-register academic vocabulary extracted from today's newspaper editorials.

    Args:
        date_str: Optional date in YYYY-MM-DD
        limit: Number of words (default: 5)
    """
    try:
        params: dict = {"limit": min(limit, 15)}
        if date_str:
            params["date_str"] = date_str

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(f"{API_BASE_URL}/api/news/vocab", params=params)
            if response.status_code == 200:
                words = response.json()
                if not words:
                    return "No vocabulary words found."
                
                lines = [f"Daily High-Register Vocabulary ({len(words)}):\n"]
                for i, w in enumerate(words, 1):
                    lines.append(f"{i}. **{w.get('word')}** ({w.get('part_of_speech') or 'n/a'}, {w.get('phonetic') or ''})")
                    lines.append(f"   Meaning: {w.get('css_meaning')}")
                    if w.get('synonyms'):
                        lines.append(f"   Synonyms: {w.get('synonyms')}")
                    if w.get('css_usage_example'):
                        lines.append(f"   CSS Essay Example: \"{w.get('css_usage_example')}\"")
                    lines.append("")
                return "\n".join(lines)
            return f"Error fetching vocab: {response.status_code}"
    except Exception as e:
        return f"Error retrieving vocabulary: {str(e)}"


# ==================== Create Agents ====================

# Single unified agent with all tools (avoids nested-agent serialisation
# that easily exceeds GitHub Models' per-request token limit).
orchestrator = Agent(
    name="PPSC Assistant",
    instructions=(
        "You are the PPSC Paper Bank assistant. "
        "Help users with MCQs, papers, scraping, and exam prep. "
        "Use the provided tools to fetch data and avoid unsupported claims. "
        "For daily news, current affairs MCQs, or editorial vocab, use get_daily_news, get_current_affairs_mcqs, and get_news_vocabulary. "
        "For requests like 'create mock series from 2020 papers' or any yearwise series request, "
        "ALWAYS use create_paper_series_from_years first because papers already exist in bank. "
        "Do NOT use get_papers or generate_paper for yearwise series creation. "
        "For follow-up confirmations like 'yes', 'yes proceed', or 'continue', "
        "continue the most recent actionable plan from conversation memory instead of asking unrelated questions. "
        "If data lookup fails, state the concrete failure and offer one direct retry path. "
        "Do not ask for MCQ category when the user requested a year-based study plan unless category is truly required. "
        "Be concise and helpful."
    ),
    model=github_model,
    tools=[
        get_categories,
        get_category_mcqs,
        get_single_mcq,
        create_paper_series_from_years,
        generate_paper,
        get_papers,
        get_paper_mcqs,
        get_daily_news,
        get_current_affairs_mcqs,
        get_news_vocabulary,
        search_internet,
        start_scraping,
    ],
)


# ==================== Helper Functions ====================

async def run_agent(
    agent: Agent,
    query: str,
    session_id: Optional[str] = None,
) -> str:
    """
    Run a specific agent with a query and optional session for conversation memory.

    Args:
        agent: The agent to run
        query: User query/message
        session_id: Optional session ID for conversation history (e.g., 'user_123')

    Returns:
        Agent's response
    """
    session = get_memory_session(session_id)

    logger.info(f"Running agent with query: {query[:100]}...")
    # Estimate tokens for context (instructions + memory + user query)
    try:
        mem_items = []
        if session is not None and hasattr(session, "get_items"):
            try:
                mem_items = await session.get_items(limit=50)
            except Exception:
                mem_items = []

        mem_text = "\n".join(
            (getattr(it, "content", str(it)) or "") for it in mem_items
        )
        instr_text = getattr(agent, "instructions", "") or ""
        context_text = instr_text + "\n\nMemory:\n" + (mem_text or "") + "\n\nUser:\n" + (query or "")
        est = estimate_tokens(context_text, getattr(agent.model, "model", None) if hasattr(agent, "model") else None)
        logger.info(f"Estimated tokens for agent request: {est} (instr={estimate_tokens(instr_text)}, memory={estimate_tokens(mem_text)}, user={estimate_tokens(query)})")

        result = await Runner.run(agent, query, session=session)
        logger.info("✓ Agent request completed successfully")
        return result.final_output
    except Exception as e:
        # Catch token-limit / 413 errors and return a friendly message
        err_str = str(e).lower()
        if "too large" in err_str or "413" in err_str or "tokens_limit" in err_str:
            logger.warning("⚠️ Request exceeded token limit — returning fallback")
            return (
                "Sorry, that request was too large for the AI model. "
                "Please try a shorter or simpler question."
            )
        handle_api_error(e)
        raise


async def run_orchestrator(
    query: str,
    session_id: Optional[str] = None,
    auth_header: Optional[str] = None,
) -> str:
    """
    Run the orchestrator with a query and optional session for conversation memory.

    Args:
        query: User query/message
        session_id: Optional session ID for conversation history (e.g., 'user_123')
        auth_header: Optional bearer authorization header propagated from API route

    Returns:
        Orchestrator's response
    """
    session = get_memory_session(session_id)

    logger.info(f"Running orchestrator with query: {query[:100]}...")
    # Estimate tokens for context (instructions + memory + user query)
    try:
        mem_items = []
        if session is not None and hasattr(session, "get_items"):
            try:
                mem_items = await session.get_items(limit=50)
            except Exception:
                mem_items = []

        mem_text = "\n".join(
            (getattr(it, "content", str(it)) or "") for it in mem_items
        )
        instr_text = getattr(orchestrator, "instructions", "") or ""
        context_text = instr_text + "\n\nMemory:\n" + (mem_text or "") + "\n\nUser:\n" + (query or "")
        est = estimate_tokens(context_text, getattr(orchestrator.model, "model", None) if hasattr(orchestrator, "model") else None)
        logger.info(f"Estimated tokens for orchestrator request: {est} (instr={estimate_tokens(instr_text)}, memory={estimate_tokens(mem_text)}, user={estimate_tokens(query)})")

        global _GLOBAL_AUTH_HEADER
        logger.info("Orchestrator auth forwarding: %s", "present" if auth_header else "missing")
        token = _CURRENT_AUTH_HEADER.set(auth_header)
        prev_global = _GLOBAL_AUTH_HEADER
        _GLOBAL_AUTH_HEADER = auth_header
        try:
            result = await Runner.run(orchestrator, query, session=session)
        finally:
            _CURRENT_AUTH_HEADER.reset(token)
            _GLOBAL_AUTH_HEADER = prev_global
        logger.info("✓ Orchestrator request completed successfully")
        output = (result.final_output or "").strip()
        if _looks_like_tool_failure_output(output):
            logger.warning("⚠️ Orchestrator produced tool-failure style output; returning deterministic fallback")
            return _deterministic_tool_failure_reply()
        return output
    except Exception as e:
        err_str = str(e).lower()
        if "too large" in err_str or "413" in err_str or "tokens_limit" in err_str:
            logger.warning("⚠️ Request exceeded token limit — returning fallback")
            return (
                "Sorry, that request was too large for the AI model. "
                "Please try a shorter or simpler question."
            )
        if "fetch" in err_str or "http" in err_str or "timeout" in err_str or "connection" in err_str:
            logger.warning("⚠️ Tool/API failure detected — returning deterministic fallback")
            return _deterministic_tool_failure_reply()
        handle_api_error(e)
        raise


async def get_session_history(session_id: str, limit: Optional[int] = None) -> List:
    """
    Get conversation history for a session.
    
    Args:
        session_id: Session ID to retrieve history for
        limit: Maximum number of items to return (optional)
    
    Returns:
        List of conversation items
    """
    session = SQLiteSession(session_id, SESSION_DB)
    items = await session.get_items(limit=limit)
    return items


async def clear_session(session_id: str) -> None:
    """
    Clear all conversation history for a session.
    
    Args:
        session_id: Session ID to clear
    """
    session = SQLiteSession(session_id, SESSION_DB)
    await session.clear_session()


# ==================== Test Function ====================

async def test_agent():
    """Test the agent system with session memory."""
    print("Testing Agent System with Session Memory")
    print("=" * 60)
    
    session_id = "test_user_123"
    
    # Test 1: Create a paper
    print("\n1. Creating a paper...")
    print("-" * 60)
    response = await run_orchestrator(
        "Create a practice paper with 10 medium difficulty computer questions",
        session_id=session_id
    )
    print(response)
    
    # Test 2: Follow-up question (testing session memory)
    print("\n2. Follow-up question (testing session memory)...")
    print("-" * 60)
    response = await run_orchestrator(
        "Show me the questions in that paper",
        session_id=session_id
    )
    print(response)
    
    # Test 3: Internet search
    print("\n3. Testing internet search...")
    print("-" * 60)
    response = await run_orchestrator(
        "Search for information about PPSC exam preparation tips",
        session_id=session_id
    )
    print(response)
    
    # Show session history
    print("\n4. Session history...")
    print("-" * 60)
    history = await get_session_history(session_id, limit=5)
    print(f"Total items in session: {len(history)}")
    
    print("\n" + "=" * 60)
    print("Test completed!")


if __name__ == "__main__":
    asyncio.run(test_agent())
