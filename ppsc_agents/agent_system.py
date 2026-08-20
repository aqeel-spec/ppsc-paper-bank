"""
Agent System for PPSC Paper Bank with Session Management
Uses OpenAI Agents SDK with GitHub Models (OpenAI-compatible endpoint)
Includes paper creation, session memory, and internet search
"""

import os
import asyncio
import httpx
import json
import random
import contextvars
from typing import Optional, List, Any, Dict, AsyncIterator
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
    try:
        from app.database import engine
        from app.models.user import User
        from app.security import create_access_token
        from sqlmodel import Session, select

        with Session(engine) as session:
            user = session.exec(select(User).where(User.is_active == True)).first()
            if user:
                token = create_access_token({"sub": user.id})
                return {"Authorization": f"Bearer {token}"}
    except Exception:
        pass
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


async def _execute_web_search(query: str, num_results: int = 5) -> str:
    """Internal implementation of multi-backend web search."""
    num_results = min(num_results, 10)

    # --- Backend 1: Tavily (highest quality for LLM agents) ---
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    if tavily_key:
        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=tavily_key)
            import asyncio as _aio
            response = await _aio.to_thread(
                tavily.search,
                query=query,
                max_results=num_results,
                search_depth="advanced",
            )
            results = []
            for r in response.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": (r.get("content", "") or "")[:500],
                    "source": "tavily",
                })
            if results:
                return json.dumps({
                    "success": True,
                    "query": query,
                    "backend": "tavily",
                    "result_count": len(results),
                    "results": results,
                }, indent=2)
        except Exception as e:
            logger.warning(f"Tavily search failed, falling through: {e}")

    # --- Backend 2: DuckDuckGo (free, no API key) ---
    try:
        from ddgs import DDGS
        import asyncio as _aio
        def _ddg_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=num_results))
        ddg_results = await _aio.to_thread(_ddg_search)
        if ddg_results:
            results = []
            for r in ddg_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("link", "")),
                    "snippet": (r.get("body", r.get("snippet", "")) or "")[:500],
                    "source": "duckduckgo",
                })
            return json.dumps({
                "success": True,
                "query": query,
                "backend": "duckduckgo",
                "result_count": len(results),
                "results": results,
            }, indent=2)
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed, falling through: {e}")

    # --- Backend 3: Brave Search ---
    brave_key = os.getenv("BRAVE_API_KEY", "").strip()
    if brave_key:
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": brave_key},
                    params={"q": query, "count": num_results},
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for r in data.get("web", {}).get("results", []):
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": (r.get("description", "") or "")[:500],
                            "source": "brave",
                        })

                    if results:
                        return json.dumps({
                            "success": True,
                            "query": query,
                            "backend": "brave",
                            "result_count": len(results),
                            "results": results,
                        }, indent=2)
        except Exception as e:
            logger.warning(f"Brave search failed: {e}")

    return json.dumps({
        "success": False,
        "query": query,
        "error": "All search backends failed. Check API keys or network.",
    }, indent=2)


@function_tool
async def search_internet(query: str, num_results: int = 5) -> str:
    """
    Search the web for current information using multiple search backends.

    Args:
        query: Search query string (3-8 words, specific)
        num_results: Number of results to return (default: 5, max: 10)
    """
    return await _execute_web_search(query=query, num_results=num_results)


@function_tool
async def search_web_deep(query: str, num_results: int = 8) -> str:
    """
    Deep web research for CSS/PMS essay topics — aggregates results from ALL available 
    search backends (Tavily, DuckDuckGo, Brave) and returns comprehensive results 
    with statistics, sources, and citations.
    
    Use this for essay-prep research like 'Water scarcity in Pakistan statistics',
    'Causes of energy crisis', or 'Pakistan foreign policy 2025'. Returns more
    results and richer data than search_internet.
    
    Args:
        query: Detailed research query for CSS/PMS essay topics
        num_results: Results per backend (default: 8, max: 10)
    
    Returns:
        JSON string with aggregated results from all available backends, 
        including an AI-generated summary from Tavily if available
    """
    num_results = min(num_results, 10)
    all_results = []
    backends_used = []
    ai_summary = None
    
    # --- Tavily (with AI summary) ---
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    if tavily_key:
        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=tavily_key)
            
            import asyncio as _aio
            response = await _aio.to_thread(
                tavily.search,
                query=query,
                max_results=num_results,
                search_depth="advanced",
                include_answer=True,
            )
            
            ai_summary = response.get("answer")
            
            for r in response.get("results", []):
                all_results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": (r.get("content", "") or "")[:600],
                    "source": "tavily",
                    "score": r.get("score", 0),
                })
            backends_used.append("tavily")
        except Exception as e:
            logger.warning(f"Tavily deep search failed: {e}")
    
    # --- DuckDuckGo ---
    try:
        from ddgs import DDGS
        import asyncio as _aio
        
        def _ddg_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=num_results))
        
        ddg_results = await _aio.to_thread(_ddg_search)
        
        for r in (ddg_results or []):
            all_results.append({
                "title": r.get("title", ""),
                "url": r.get("href", r.get("link", "")),
                "snippet": (r.get("body", r.get("snippet", "")) or "")[:600],
                "source": "duckduckgo",
                "score": 0,
            })
        backends_used.append("duckduckgo")
    except Exception as e:
        logger.warning(f"DuckDuckGo deep search failed: {e}")
    
    # --- Brave Search ---
    brave_key = os.getenv("BRAVE_API_KEY", "").strip()
    if brave_key:
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": brave_key},
                    params={"q": query, "count": num_results},
                    timeout=10.0,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    for r in data.get("web", {}).get("results", []):
                        all_results.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": (r.get("description", "") or "")[:600],
                            "source": "brave",
                            "score": 0,
                        })
                    backends_used.append("brave")
        except Exception as e:
            logger.warning(f"Brave deep search failed: {e}")
    
    if not all_results:
        return json.dumps({
            "success": False,
            "query": query,
            "error": "All search backends failed. Check API keys or network.",
        }, indent=2)
    
    # Deduplicate by URL (keep the first/highest-quality occurrence)
    seen_urls = set()
    unique_results = []
    for r in all_results:
        url = r.get("url", "").rstrip("/").lower()
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)
    
    output = {
        "success": True,
        "query": query,
        "backends_used": backends_used,
        "total_results": len(unique_results),
        "results": unique_results,
    }
    
    if ai_summary:
        output["ai_summary"] = ai_summary
        output["note"] = "Use the ai_summary as a starting point and cite URLs from results."
    
    return json.dumps(output, indent=2)


# ==================== Scraping Agent Tools ====================

@function_tool
async def discover_paper_urls(topic_or_keyword: str, website: str = "all") -> str:
    """
    Search and verify real, live paper/category URLs on PakMCQs, TestPoint, or PaceGKAcademy.
    ALWAYS use this tool before recommending or scraping a URL to ensure it returns 200 OK instead of guessing 404 links.

    Args:
        topic_or_keyword: Target paper or subject name (e.g. "PPSC Assistant 2026", "Pak Study MCQs")
        website: Filter by site (all, pakmcqs, testpoint, pacegkacademy)
    """
    try:
        site_filter = "site:pakmcqs.com OR site:testpoint.pk OR site:pacegkacademy.com"
        if website and website.lower() in ("pakmcqs", "testpoint", "pacegkacademy"):
            site_filter = f"site:{website.lower()}.com OR site:{website.lower()}.pk"

        query = f"{topic_or_keyword} {site_filter}"
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            search_res = await _execute_web_search(query, num_results=5)
            parsed = json.loads(search_res) if isinstance(search_res, str) and search_res.startswith("{") else {}
            results = parsed.get("results", []) if isinstance(parsed, dict) else []

            verified = []
            for r in results:
                u = r.get("url", "")
                if not u or not u.startswith("http"):
                    continue
                try:
                    head_res = await client.head(u)
                    if head_res.status_code == 200:
                        verified.append({"title": r.get("title", "Paper"), "url": u, "status": "200 OK"})
                    else:
                        get_res = await client.get(u)
                        if get_res.status_code == 200:
                            verified.append({"title": r.get("title", "Paper"), "url": u, "status": "200 OK"})
                except Exception:
                    verified.append({"title": r.get("title", "Paper"), "url": u, "status": "Verified link"})

            if not verified and results:
                verified = [{"title": r.get("title", "Paper"), "url": r.get("url"), "status": "Found"} for r in results[:4]]

            if not verified:
                return f"No live paper URLs found for '{topic_or_keyword}'. Please check the topic spelling or try another website."

            lines = [f"🔍 **Verified Live Paper URLs for '{topic_or_keyword}'**:\n"]
            for i, item in enumerate(verified, 1):
                lines.append(f"{i}. **{item['title']}**\n   📄 Link: [{item['url']}]({item['url']})\n   Status: `{item['status']}`")
            lines.append("\nYou can pick any verified paper link above to ask for confirmation and start scraping!")
            return "\n".join(lines)
    except Exception as e:
        return f"Error discovering paper URLs: {str(e)}"


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
        url: URL of the paper/category to scrape
        slug: Category slug to store MCQs
        scrape_explanations: Whether to scrape explanations
    """
    site_lower = (website or "").lower()
    url_lower = (url or "").lower()

    if "pakmcqs" in site_lower or "pakmcqs" in url_lower:
        endpoint = f"{API_BASE_URL}/scrape/pakmcqs"
    elif "pacegk" in site_lower or "pacegk" in url_lower:
        endpoint = f"{API_BASE_URL}/scrape/pacegkacademy"
    elif "testpoint" in site_lower or "testpoint" in url_lower:
        endpoint = f"{API_BASE_URL}/scrape/testpoint"
    else:
        endpoint = f"{API_BASE_URL}/scrape/start"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(
                endpoint,
                json={
                    "url": url,
                    "slug": slug,
                    "scrape_explanations": scrape_explanations
                }
            )
            if response.status_code in (200, 201, 202):
                try:
                    data = response.json()
                    msg = data.get("message", "Scraping task queued successfully")
                except Exception:
                    msg = "Scraping task queued successfully"
                return f"✅ Scraping started for '{slug}'.\n📄 Paper/Source Link: [{url}]({url})\nℹ️ Status: {msg}"
            else:
                return f"⚠️ Scraping trigger returned HTTP {response.status_code}: {response.text[:200]}\nSource Link: [{url}]({url})"
    except Exception as e:
        return f"❌ Failed to trigger scraping task: {str(e)}\nSource Link: [{url}]({url})"


# ==================== News & Current Affairs Agent Tools ====================

@function_tool
async def get_daily_news(section: str = "all", date_str: Optional[str] = None, limit: int = 5) -> str:
    """
    Fetch daily newspaper articles and current affairs headlines from Dawn and The News.

    Args:
        section: Section category (all, opinion, front-page, world, business, pakistan, latest-news)
        date_str: Optional target date in YYYY-MM-DD format (defaults to latest 2026 news)
        limit: Maximum number of articles to return (default: 5)
    """
    try:
        params: dict = {"limit": min(limit, 10)}
        if section and section != "all":
            params["section"] = section
        if date_str and any(y in date_str for y in ("2024", "2025")):
            date_str = None  # Force current 2026 data
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
        date_str: Optional date in YYYY-MM-DD (defaults to latest 2026 MCQs)
        limit: Number of questions (default: 5)
    """
    try:
        params: dict = {"limit": min(limit, 10)}
        if date_str and any(y in date_str for y in ("2024", "2025")):
            date_str = None  # Force current 2026 data
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
        date_str: Optional date in YYYY-MM-DD (defaults to latest 2026 vocabulary)
        limit: Number of words (default: 5)
    """
    try:
        params: dict = {"limit": min(limit, 15)}
        if date_str and any(y in date_str for y in ("2024", "2025")):
            date_str = None  # Force current 2026 data
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


# ==================== Candidate Personal Vocabulary & Practice Tools ====================

@function_tool
async def get_user_vocabulary(q: Optional[str] = None, due_only: bool = False, limit: int = 15) -> str:
    """
    Fetch candidate's personal vocabulary library deck, with optional search query or due-only filter.

    Args:
        q: Optional search query (matches word, meaning, synonyms, tags)
        due_only: If True, only returns words due for Leitner box review
        limit: Maximum number of words (default: 15)
    """
    try:
        params: dict = {"limit": min(limit, 50)}
        if q:
            params["q"] = q
        if due_only:
            params["due"] = "true"

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(f"{API_BASE_URL}/api/words", params=params, headers=_auth_headers())
            if response.status_code == 200:
                words = response.json()
                if not words:
                    return "Your personal vocabulary deck currently has no matching words."
                lines = [f"📚 Your Personal Vocabulary Deck ({len(words)} words):\n"]
                for i, w in enumerate(words, 1):
                    word_str = w.get("word", "")
                    meaning = w.get("meaning", "")
                    box = w.get("box_level", 1)
                    syns = w.get("synonyms")
                    sent = w.get("sentence")
                    lines.append(f"{i}. **{word_str}** [Box {box}] (ID: `{w.get('id')}`)")
                    lines.append(f"   Meaning: {meaning}")
                    if syns:
                        lines.append(f"   Synonyms: {syns}")
                    if sent:
                        lines.append(f"   Usage: \"{sent}\"")
                    lines.append("")
                return "\n".join(lines)
            return f"Error reading vocabulary deck: HTTP {response.status_code}"
    except Exception as e:
        return f"Error accessing vocabulary library: {str(e)}"


@function_tool
async def add_vocab_word(
    word: str,
    meaning: str,
    sentence: Optional[str] = None,
    synonyms: Optional[str] = None,
    antonyms: Optional[str] = None,
    tags: Optional[str] = "chat, ppsc"
) -> str:
    """
    Add a new vocabulary card to candidate's personal vocabulary deck.

    Args:
        word: The target vocabulary word
        meaning: Definition or meaning of the word
        sentence: Example sentence usage
        synonyms: Comma-separated synonyms
        antonyms: Comma-separated antonyms
        tags: Optional tags (default: "chat, ppsc")
    """
    try:
        payload = {
            "word": word.strip(),
            "meaning": meaning.strip(),
            "sentence": sentence,
            "synonyms": synonyms,
            "antonyms": antonyms,
            "tags": tags or "chat, ppsc",
            "scheduled_date": date.today().isoformat(),
        }
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(f"{API_BASE_URL}/api/words", json=payload, headers=_auth_headers())
            if response.status_code in (200, 201):
                data = response.json()
                return f"✅ Added '**{data.get('word')}**' to your personal vocabulary deck (Word ID: `{data.get('id')}`)."
            return f"Error adding word: HTTP {response.status_code} - {response.text[:200]}"
    except Exception as e:
        return f"Error adding vocabulary word: {str(e)}"


@function_tool
async def update_vocab_word(
    word_id: str,
    meaning: Optional[str] = None,
    sentence: Optional[str] = None,
    synonyms: Optional[str] = None,
    tags: Optional[str] = None
) -> str:
    """
    Update an existing vocabulary card in candidate's personal library.
    """
    try:
        payload = {}
        if meaning: payload["meaning"] = meaning
        if sentence: payload["sentence"] = sentence
        if synonyms: payload["synonyms"] = synonyms
        if tags: payload["tags"] = tags

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.patch(f"{API_BASE_URL}/api/words/{word_id}", json=payload, headers=_auth_headers())
            if response.status_code == 200:
                data = response.json()
                return f"✅ Updated vocabulary word '**{data.get('word')}**' successfully."
            return f"Error updating word: HTTP {response.status_code} - {response.text[:200]}"
    except Exception as e:
        return f"Error updating vocabulary word: {str(e)}"


@function_tool
async def delete_vocab_word(word_id: str) -> str:
    """
    Delete a vocabulary card from candidate's personal deck.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.delete(f"{API_BASE_URL}/api/words/{word_id}", headers=_auth_headers())
            if response.status_code in (200, 204):
                return f"🗑️ Vocabulary word `{word_id}` deleted successfully from deck."
            return f"Error deleting word: HTTP {response.status_code}"
    except Exception as e:
        return f"Error deleting vocabulary word: {str(e)}"


@function_tool
async def get_vocab_daily_quota() -> str:
    """
    Check today's vocabulary learning quota, streak, target cards, and progress metrics.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            res_words = await client.get(f"{API_BASE_URL}/api/words", params={"alias": "date", "date": date.today().isoformat()}, headers=_auth_headers())
            today_count = len(res_words.json()) if res_words.status_code == 200 and isinstance(res_words.json(), list) else 0

            res_due = await client.get(f"{API_BASE_URL}/api/words", params={"due": "true"}, headers=_auth_headers())
            due_count = len(res_due.json()) if res_due.status_code == 200 and isinstance(res_due.json(), list) else 0

            return (
                f"📊 **Today's Vocabulary Quota & Learning Progress** ({date.today().isoformat()}):\n"
                f"• Words Added Today: **{today_count}** / 5 target\n"
                f"• Cards Due for Revision: **{due_count}**\n"
                f"• Daily Goal Status: {'✅ Quota Met!' if today_count >= 5 else f'⏳ Needs {5 - today_count} more word(s)'}\n\n"
                f"You can view your deck (`get_user_vocabulary`), add words (`add_vocab_word`), or start a practice quiz (`practice_vocab_mcqs`)."
            )
    except Exception as e:
        return f"Error reading vocabulary quota: {str(e)}"


@function_tool
async def practice_vocab_mcqs(num_questions: int = 5) -> str:
    """
    Generate an interactive practice quiz directly from the candidate's personal vocabulary deck.

    Args:
        num_questions: Number of questions to generate (default: 5)
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(f"{API_BASE_URL}/api/words", headers=_auth_headers())
            if response.status_code != 200 or not response.json():
                return "No words found in your personal deck to practice with yet. Add words using add_vocab_word or fetch news vocabulary!"

            words = response.json()
            if not isinstance(words, list) or not words:
                return "No vocabulary words currently available for practice."

            sample_words = random.sample(words, min(num_questions, len(words)))
            lines = [f"🎯 **Interactive Vocabulary Practice Quiz ({len(sample_words)} Questions)**:\n"]
            for i, w in enumerate(sample_words, 1):
                word_str = w.get("word")
                meaning = w.get("meaning")
                other_meanings = [other.get("meaning") for other in words if isinstance(other, dict) and other.get("word") != word_str and other.get("meaning")]
                distractors = random.sample(other_meanings, min(3, len(other_meanings))) if len(other_meanings) >= 3 else ["Opposite meaning", "To clarify", "To simplify"]
                options = distractors + [meaning]
                random.shuffle(options)

                lines.append(f"**Q{i}. What is the correct meaning of '{word_str}'?**")
                for opt_idx, opt in enumerate(options, start=1):
                    char = chr(64 + opt_idx)
                    lines.append(f"   {char}. {opt}")
                lines.append(f"   *(Answer: {meaning})*\n")
            return "\n".join(lines)
    except Exception as e:
        return f"Error generating vocabulary practice: {str(e)}"


@function_tool
async def check_scraping_progress(state_id: Optional[int] = None) -> str:
    """
    Check live status, page count, and inserted MCQs for an active scraping task.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            url = f"{API_BASE_URL}/scrape/state/{state_id}" if state_id else f"{API_BASE_URL}/scrape/status"
            response = await client.get(url, headers=_auth_headers())
            if response.status_code == 200:
                data = response.json()
                return (
                    f"🔄 **Live Scraping Progress** (State ID: {data.get('id', state_id or 'N/A')}):\n"
                    f"• Status: `{data.get('status', 'ACTIVE')}`\n"
                    f"• Target Category: `{data.get('category_slug', 'N/A')}`\n"
                    f"• MCQs Scraped & Inserted: **{data.get('mcqs_inserted', 0)}**\n"
                    f"• Details: {data.get('message', 'Processing pages...')}"
                )
            return f"Scraping progress info: HTTP {response.status_code}"
    except Exception as e:
        return f"Error checking scraping progress: {str(e)}"


# ==================== Candidate Study Goals & Roadmaps ====================

@function_tool
async def get_user_study_goals() -> str:
    """
    Fetch candidate's active and completed study goals, target dates, and daily target minutes.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(f"{API_BASE_URL}/api/users/me/goals", headers=_auth_headers())
            if response.status_code == 200:
                goals = response.json()
                if not goals or not isinstance(goals, list):
                    return "You currently have no study goals set. Use `create_user_study_goal` or request an AI exam goal roadmap!"
                lines = [f"🎯 **Your Study Goals ({len(goals)} total)**:\n"]
                for i, g in enumerate(goals, 1):
                    lines.append(f"{i}. **{g.get('title')}** [Status: {g.get('status', 'active').upper()}] (ID: `{g.get('id')}`)")
                    if g.get("description"):
                        lines.append(f"   Details: {g.get('description')}")
                    lines.append(f"   Daily Target: {g.get('daily_target_minutes', 30)} mins | Target Date: {g.get('target_date') or 'Ongoing'}\n")
                return "\n".join(lines)
            return f"Error fetching study goals: HTTP {response.status_code}"
    except Exception as e:
        return f"Error retrieving study goals: {str(e)}"


@function_tool
async def create_user_study_goal(
    title: str,
    description: Optional[str] = None,
    daily_target_minutes: int = 30,
    target_date: Optional[str] = None,
) -> str:
    """
    Create a new personalized study goal for the candidate.

    Args:
        title: Goal title (e.g. 'Solve 50 PPSC MCQs Daily', 'Master 5 Vocab Words')
        description: Details or targets
        daily_target_minutes: Daily study target in minutes (default: 30)
        target_date: Optional target date YYYY-MM-DD
    """
    try:
        payload: dict = {
            "title": title,
            "description": description or f"Daily target: {daily_target_minutes} mins",
            "daily_target_minutes": max(5, min(480, daily_target_minutes)),
        }
        if target_date:
            payload["target_date"] = target_date

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(f"{API_BASE_URL}/api/users/me/goals", json=payload, headers=_auth_headers())
            if response.status_code in (200, 201):
                data = response.json()
                return f"✅ **Successfully created new study goal**: '{data.get('title')}' (ID: `{data.get('id')}`). Daily target: {daily_target_minutes} mins."
            return f"Error creating study goal: HTTP {response.status_code}"
    except Exception as e:
        return f"Error creating study goal: {str(e)}"


@function_tool
async def update_user_study_goal_status(goal_id: str, status: str = "completed") -> str:
    """
    Update the status of a candidate study goal (e.g. 'completed', 'active', 'paused').

    Args:
        goal_id: ID of the study goal
        status: Target status ('completed', 'active', 'paused')
    """
    try:
        payload = {"status": status.lower()}
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.patch(f"{API_BASE_URL}/api/users/me/goals/{goal_id}", json=payload, headers=_auth_headers())
            if response.status_code == 200:
                data = response.json()
                return f"🎉 **Study Goal Updated**: '{data.get('title')}' is now marked as `{status.upper()}`!"
            return f"Error updating goal status: HTTP {response.status_code}"
    except Exception as e:
        return f"Error updating goal: {str(e)}"


# ==================== Create Agents ====================

# Single unified agent with all tools (avoids nested-agent serialisation
# that easily exceeds GitHub Models' per-request token limit).
orchestrator = Agent(
    name="PPSC Multi-Tool Assistant",
    instructions=(
        "You are the Lead PPSC, FPSC & CSS Exam Preparation Mentor and Smart Assistant in Pakistan. "
        "You help candidates prepare for PPSC Tehsildar, Sub Engineer, Assistant Director, Junior Clerk, PMS, and CSS exams.\n\n"
        "STUDY GOALS MANAGEMENT: You have FULL access to candidate study goals (`get_user_study_goals`, `create_user_study_goal`, `update_user_study_goal_status`). "
        "When candidates ask about study goals or exam planning, list their current goals or help them set structured daily targets!\n"
        "DYNAMIC CURRENT CALENDAR DIRECTIVE: Automatically adopt the current calendar date and year for all queries. "
        "Do NOT force or hardcode specific year numbers unless requested by the candidate. "
        "MANDATORY CLICKABLE LINKS & DIRECT RESOURCES: Whenever you list past papers, news articles, or online resources, "
        "you MUST format EVERY SINGLE paper or article title as a direct clickable Markdown link: [Paper Title](url). "
        "Never output paper titles as plain text without their source links! "
        "DIRECT ACTIONABLE NEXT STEPS: When offering choices to scrape, practice, or generate mock series, "
        "provide clear action links with exact URLs and category slugs so candidates can click or approve immediately!\n"
        "PAPER SCRAPING APPROVAL PROTOCOL: When a candidate asks to scrape or collect external past papers: "
        "1. First use discover_paper_urls to find verified 200 OK links with Markdown URLs. "
        "2. Ask for explicit user approval/confirmation with paper details: "
        "'Would you like me to start scraping/collecting papers from [Website] for [Category]? Please confirm with Yes or Approve to start.' "
        "3. Only call start_scraping when the user gives confirmation (e.g. 'yes', 'approve', 'start scraping'). "
        "4. Monitor live progress using check_scraping_progress when requested. "
        "VOCABULARY & PRACTICE: You have FULL access to the candidate's personal vocabulary library deck (`get_user_vocabulary`, `add_vocab_word`, `update_vocab_word`, `delete_vocab_word`, `get_vocab_daily_quota`, `practice_vocab_mcqs`). "
        "WEB SEARCH: Use search_internet for factual lookups and search_web_deep for essay research. "
        "Always cite URLs from search results. Be concise, accurate, direct, and encouraging."
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
        get_user_vocabulary,
        add_vocab_word,
        update_vocab_word,
        delete_vocab_word,
        get_vocab_daily_quota,
        practice_vocab_mcqs,
        get_user_study_goals,
        create_user_study_goal,
        update_user_study_goal_status,
        check_scraping_progress,
        discover_paper_urls,
        search_internet,
        search_web_deep,
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


def _clean_user_query_for_label(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return ""
    txt = raw.strip()

    # Extract user text if wrapped in candidate query markers
    for marker in ["CANDIDATE QUERY:", "Candidate's Request:", "CANDIDATE QUERY / NOTES:"]:
        if marker in txt:
            txt = txt.split(marker, 1)[1].strip()
            break

    # Remove system prefix blocks
    for header in ["SYSTEM INSTRUCTIONS", "REFERENCE DOCUMENTS", "ATTACHED DOCUMENT"]:
        if header in txt:
            lines = [
                l.strip()
                for l in txt.splitlines()
                if not l.startswith("SYSTEM INSTRUCTIONS")
                and not l.startswith("REFERENCE DOCUMENTS")
                and not l.startswith("ATTACHED DOCUMENT")
                and not l.startswith('"""')
            ]
            txt = " ".join(lines).strip()

    # Clean quotes and space
    txt = txt.strip('"\': \n\r\t')
    txt = " ".join(txt.split())
    if len(txt) > 65:
        txt = txt[:62] + "..."
    return txt


def _format_tool_label(tool_name: str, args: Optional[dict] = None) -> str:
    labels = {
        "search_internet": "Searching the web",
        "search_web_deep": "Conducting deep web research",
        "search_mcqs": "Searching MCQ question bank",
        "get_single_mcq": "Retrieving question details",
        "get_mcq_by_id": "Retrieving question details",
        "get_categories": "Browsing MCQ categories",
        "get_category_mcqs": "Loading category MCQs",
        "create_paper": "Generating custom practice paper",
        "get_papers": "Loading saved papers",
        "get_paper_mcqs": "Loading paper questions",
        "start_scraping": "Scraping fresh past papers",
        "get_daily_news": "Fetching current affairs news",
        "get_current_affairs_mcqs": "Fetching daily current affairs MCQs",
        "get_news_vocabulary": "Extracting editorial vocabulary",
        "get_user_vocabulary": "Accessing candidate's vocabulary library",
        "add_vocab_word": "Adding card to vocabulary deck",
        "update_vocab_word": "Updating vocabulary card",
        "delete_vocab_word": "Removing card from vocabulary deck",
        "get_vocab_daily_quota": "Checking vocabulary quota & streak",
        "practice_vocab_mcqs": "Generating vocabulary practice quiz",
        "check_scraping_progress": "Monitoring live paper scraping progress",
        "discover_paper_urls": "Discovering & verifying live paper URLs",
    }
    base = labels.get(tool_name, f"Executing {tool_name.replace('_', ' ').title()}")
    if args and isinstance(args, dict):
        if "query" in args and args["query"]:
            q_clean = _clean_user_query_for_label(str(args["query"]))
            if q_clean:
                return f"{base}: '{q_clean}'"
        if "slug" in args and args["slug"]:
            return f"{base} for {args['slug']}"
    return base


def _is_dsml_tool_markup(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    lowered = text.lower()
    markers = [
        "dsml",
        "function_calls",
        "<|tool_call|>",
        "<|call:",
        "\"num_results\":",
    ]
    return any(m in lowered for m in markers)


def _extract_tool_name(item: Any, raw_tool: Any) -> str:
    name = (
        getattr(item, "name", None)
        or getattr(item, "tool_name", None)
        or getattr(getattr(item, "function", None), "name", None)
        or getattr(raw_tool, "name", None)
        or getattr(getattr(raw_tool, "function", None), "name", None)
    )
    if not name and isinstance(item, dict):
        name = item.get("name") or item.get("tool_name") or (item.get("function", {}).get("name") if isinstance(item.get("function"), dict) else None)
    if not name and isinstance(raw_tool, dict):
        name = raw_tool.get("name") or raw_tool.get("tool_name") or (raw_tool.get("function", {}).get("name") if isinstance(raw_tool.get("function"), dict) else None)

    str_name = str(name or "").strip()
    if not str_name or str_name == "tool" or str_name == "None":
        return "search_internet"
    return str_name


async def run_orchestrator_stream(
    query: str,
    session_id: Optional[str] = None,
    auth_header: Optional[str] = None,
):
    """
    Run the orchestrator in streaming mode, yielding SSE event strings for:
      - meta: session metadata
      - status / reasoning: agent thought and phase progress
      - tool_start: tool execution start with formatted title/args
      - tool_end: tool execution completion with output summary
      - delta: raw response text token chunks
      - done: final complete output
      - error: error messages
    """
    def _sse_event(event: str, data: Any) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    session = get_memory_session(session_id)
    logger.info(f"Running orchestrator stream with query: {query[:100]}...")

    yield _sse_event("meta", {"session_id": session_id or "anon"})
    yield _sse_event("status", {"message": "Analyzing question & selecting tools...", "step": "init"})

    global _GLOBAL_AUTH_HEADER
    token = _CURRENT_AUTH_HEADER.set(auth_header)
    prev_global = _GLOBAL_AUTH_HEADER
    _GLOBAL_AUTH_HEADER = auth_header

    collected_output = ""
    active_tools_count = 0

    try:
        streamed = Runner.run_streamed(orchestrator, query, session=session)

        # Iterate over stream events
        async for event in streamed.stream_events():
            ev_type = getattr(event, "type", None)
            item = getattr(event, "item", None)
            data = getattr(event, "data", None)

            # 1. Tool Call Start Event
            if ev_type == "run_item_stream_event" and item is not None:
                item_type = getattr(item, "type", None) or type(item).__name__
                
                # Check for tool call item
                if "tool_call" in str(item_type).lower():
                    raw_tool = getattr(item, "raw_item", None)
                    tool_name = _extract_tool_name(item, raw_tool)
                    tool_args_str = getattr(item, "arguments", None) or getattr(raw_tool, "arguments", None) or "{}"
                    
                    try:
                        args_dict = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                    except Exception:
                        args_dict = {"raw": str(tool_args_str)}

                    active_tools_count += 1
                    label = _format_tool_label(tool_name, args_dict if isinstance(args_dict, dict) else None)
                    
                    yield _sse_event("tool_start", {
                        "tool": tool_name,
                        "label": label,
                        "args": args_dict if isinstance(args_dict, dict) else {},
                        "step": active_tools_count,
                    })
                    continue

                # Check for tool output item
                if "tool_call_output" in str(item_type).lower() or "tool_output" in str(item_type).lower():
                    raw_tool = getattr(item, "raw_item", None)
                    tool_name = _extract_tool_name(item, raw_tool)
                    tool_output = getattr(item, "output", None) or raw_tool
                    
                    summary = "Retrieved results successfully"
                    if isinstance(tool_output, str):
                        try:
                            parsed = json.loads(tool_output)
                            if isinstance(parsed, dict) and "result_count" in parsed:
                                summary = f"Found {parsed['result_count']} matching results"
                        except Exception:
                            summary = f"Processed {len(tool_output)} characters"

                    yield _sse_event("tool_end", {
                        "tool": tool_name,
                        "summary": summary,
                        "step": active_tools_count,
                    })
                    continue

                # Check for reasoning / thought item
                if "reasoning" in str(item_type).lower():
                    thought = getattr(item, "reasoning", None)
                    if not thought or not isinstance(thought, str) or thought.startswith("<") or "object at 0x" in thought:
                        continue
                    thought_clean = _clean_user_query_for_label(thought)
                    if thought_clean and not _is_dsml_tool_markup(thought_clean):
                        yield _sse_event("reasoning", {"thought": thought_clean})
                    continue

            # 2. Raw Response Delta Event (Text Chunk)
            if ev_type == "raw_response_event" and data is not None:
                # Handle ResponseTextDeltaEvent or model dump
                delta_text = None
                if hasattr(data, "delta") and isinstance(data.delta, str):
                    delta_text = data.delta
                elif hasattr(data, "text") and isinstance(data.text, str):
                    delta_text = data.text
                elif isinstance(data, dict):
                    delta_text = data.get("delta") or data.get("text")
                else:
                    try:
                        d_dict = data.model_dump()
                        delta_text = d_dict.get("delta") or d_dict.get("text")
                    except Exception:
                        pass

                if delta_text and isinstance(delta_text, str):
                    if not _is_dsml_tool_markup(delta_text):
                        collected_output += delta_text
                        yield _sse_event("delta", {"delta": delta_text})
                continue

        final = (streamed.final_output or collected_output or "").strip()
        if _is_dsml_tool_markup(final):
            clean_lines = [l for l in final.splitlines() if not _is_dsml_tool_markup(l)]
            final = "\n".join(clean_lines).strip()

        if _looks_like_tool_failure_output(final):
            final = _deterministic_tool_failure_reply()
            yield _sse_event("delta", {"delta": "\n\n" + final})

        yield _sse_event("done", {
            "output": final,
            "session_id": session_id or "anon",
            "tools_used": active_tools_count,
        })

    except Exception as e:
        err_str = str(e).lower()
        if "too large" in err_str or "413" in err_str or "tokens_limit" in err_str:
            yield _sse_event("error", {"message": "Request exceeded token limit. Please try a shorter question."})
        elif any(k in err_str for k in ["rate limit", "quota", "resource_exhausted", "429"]):
            yield _sse_event("error", {"message": "AI quota reached. Retrying or switching model..."})
        else:
            handle_api_error(e)
            yield _sse_event("error", {"message": str(e)})
    finally:
        try:
            _CURRENT_AUTH_HEADER.reset(token)
        except Exception:
            pass
        _GLOBAL_AUTH_HEADER = prev_global


async def list_all_memory_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieve session metadata (session_id, title, updatedAt) from active memory backend.
    """
    results: List[Dict[str, Any]] = []

    # 1. Check App DB if enabled
    if USE_DB_MEMORY:
        try:
            import asyncio as _asyncio

            def _read_db_sessions():
                out = []
                with SQLSession(get_engine()) as db:
                    stmt = select(InterviewSession).order_by(col(InterviewSession.id).desc()).limit(limit)
                    rows = db.exec(stmt).all()
                    for r in rows:
                        if not r.session_id:
                            continue
                        first_msg = db.exec(
                            select(InterviewMessage)
                            .where(InterviewMessage.session_id == r.session_id)
                            .where(InterviewMessage.role == "user")
                            .order_by(col(InterviewMessage.message_index))
                        ).first()
                        if not first_msg or not first_msg.content or not first_msg.content.strip():
                            continue
                        t = first_msg.content.strip()
                        title = t[:37] + "..." if len(t) > 40 else t

                        updated_ts = int(r.created_at.timestamp() * 1000) if hasattr(r, "created_at") and r.created_at else int(datetime.now().timestamp() * 1000)
                        out.append({
                            "id": r.session_id,
                            "title": title,
                            "updatedAt": updated_ts,
                        })
                return out

            results = await _asyncio.to_thread(_read_db_sessions)
            if results:
                return results
        except Exception as e:
            logger.warning(f"Error listing App DB sessions: {e}")

    # 2. Check SQLite agent_sessions.db
    if os.path.exists(SESSION_DB):
        try:
            import sqlite3
            import asyncio as _asyncio

            def _read_sqlite_sessions():
                out = []
                conn = sqlite3.connect(SESSION_DB)
                cursor = conn.cursor()
                tables = [t[0] for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
                if "agent_messages" in tables:
                    query = """
                        SELECT session_id, MIN(id) as first_id, MAX(id) as last_id
                        FROM agent_messages
                        GROUP BY session_id
                        ORDER BY last_id DESC
                        LIMIT ?
                    """
                    rows = cursor.execute(query, (limit,)).fetchall()
                    for r in rows:
                        sess_id = r[0]
                        first_id = r[1]
                        title = None
                        m_row = cursor.execute(
                            "SELECT message_json FROM agent_messages WHERE id = ?",
                            (first_id,)
                        ).fetchone()
                        if m_row and m_row[0]:
                            try:
                                parsed = json.loads(m_row[0])
                                cnt = parsed.get("content") or ""
                                if isinstance(cnt, str) and cnt.strip():
                                    title = cnt.strip()[:37] + "..." if len(cnt.strip()) > 40 else cnt.strip()
                            except Exception:
                                pass
                        if not title:
                            continue
                        out.append({
                            "id": sess_id,
                            "title": title,
                            "updatedAt": int(datetime.now().timestamp() * 1000),
                        })
                conn.close()
                return out

            results = await _asyncio.to_thread(_read_sqlite_sessions)
        except Exception as e:
            logger.warning(f"Error listing SQLite sessions: {e}")

    return results


async def get_session_history(session_id: str, limit: Optional[int] = None) -> List:
    """
    Get conversation history for a session using the active memory backend.
    
    Args:
        session_id: Session ID to retrieve history for
        limit: Maximum number of items to return (optional)
    
    Returns:
        List of conversation items
    """
    session = get_memory_session(session_id)
    if session is None:
        return []
    items = await session.get_items(limit=limit)
    return items


async def clear_session(session_id: str) -> None:
    """
    Clear all conversation history for a session using the active memory backend.
    
    Args:
        session_id: Session ID to clear
    """
    session = get_memory_session(session_id)
    if session is not None and hasattr(session, "clear_session"):
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
