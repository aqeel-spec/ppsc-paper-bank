"""Agent HTTP routes.

These routes expose the multi-tool orchestrator (papers, MCQs, scraping, study)
over HTTP from the main API server.

This duplicates the functionality of the standalone `agent_service.py`, but as a
router so you can run everything in one process.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from jose import JWTError
from sqlmodel import Session
from pydantic import BaseModel, Field

from ppsc_agents import run_orchestrator, run_orchestrator_stream, get_session_history, list_all_memory_sessions, clear_session
from app.models.user import User
from app.database import get_session
from app.security import create_access_token, decode_token, get_optional_user


router = APIRouter(prefix="/agent", tags=["Agent"])
logger = logging.getLogger(__name__)


class AgentChatRequest(BaseModel):
    query: Optional[str] = Field(default=None, description="User message")
    message: Optional[str] = Field(default=None, description="Alias for query")
    session_id: Optional[str] = Field(
        default=None,
        description="Stable session identifier used for memory (cookie/session).",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional frontend metadata (client, paper_id, etc).",
    )


class AgentChatResponse(BaseModel):
    session_id: str
    answer: str


def _issue_auth_from_user_id(user_id: Optional[str], db: Session) -> Optional[str]:
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return f"Bearer {create_access_token({'sub': user.id})}"


def _issue_auth_from_refresh_token(refresh_token: Optional[str], db: Session) -> Optional[str]:
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        return None
    token_val = refresh_token.strip()
    if token_val.lower().startswith("bearer "):
        token_val = token_val[7:].strip()
    if not token_val:
        return None
    try:
        payload = decode_token(token_val)
    except JWTError:
        return None
    if payload.get("type") != "refresh":
        return None
    return _issue_auth_from_user_id(payload.get("sub"), db)


@router.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "offline": "1" if os.getenv("PPSC_OFFLINE") == "1" else "0",
    }


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    payload: AgentChatRequest,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_session),
) -> AgentChatResponse:
    session_id = payload.session_id or "anon"
    query = (payload.query or payload.message or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="query (or message) is required")
    auth_header = request.headers.get("authorization")
    if not auth_header and payload.metadata:
        meta_auth = payload.metadata.get("authorization") or payload.metadata.get("auth_header")
        access_token = payload.metadata.get("access_token")
        refresh_token = payload.metadata.get("refresh_token")
        if isinstance(meta_auth, str) and meta_auth.strip():
            auth_header = meta_auth.strip()
        elif isinstance(access_token, str) and access_token.strip():
            auth_header = f"Bearer {access_token.strip()}"
        else:
            auth_header = _issue_auth_from_refresh_token(refresh_token, db)

    # If request is authenticated via cookie/alternate header, forward a valid bearer token to tools.
    if not auth_header and current_user is not None:
        auth_header = f"Bearer {create_access_token({'sub': current_user.id})}"

    # Fallback: derive auth from refresh_token cookie (common in Next.js proxy flows).
    if not auth_header:
        auth_header = _issue_auth_from_refresh_token(request.cookies.get("refresh_token"), db)

    # Fallback: if session_id carries canonical user:<uuid> pattern, derive user auth.
    if not auth_header and session_id.startswith("user:"):
        auth_header = _issue_auth_from_user_id(session_id.split(":", 1)[1], db)

    logger.info("/agent/chat auth received: %s", "present" if auth_header else "missing")
    answer = await run_orchestrator(query, session_id=session_id, auth_header=auth_header)
    return AgentChatResponse(session_id=session_id, answer=answer)


@router.post("/chat/stream")
@router.post("/stream")
async def agent_chat_stream(
    payload: AgentChatRequest,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_session),
):
    session_id = payload.session_id or "anon"
    query = (payload.query or payload.message or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="query (or message) is required")
    auth_header = request.headers.get("authorization")
    if not auth_header and payload.metadata:
        meta_auth = payload.metadata.get("authorization") or payload.metadata.get("auth_header")
        access_token = payload.metadata.get("access_token")
        refresh_token = payload.metadata.get("refresh_token")
        if isinstance(meta_auth, str) and meta_auth.strip():
            auth_header = meta_auth.strip()
        elif isinstance(access_token, str) and access_token.strip():
            auth_header = f"Bearer {access_token.strip()}"
        else:
            auth_header = _issue_auth_from_refresh_token(refresh_token, db)

    if not auth_header and current_user is not None:
        auth_header = f"Bearer {create_access_token({'sub': current_user.id})}"

    if not auth_header:
        auth_header = _issue_auth_from_refresh_token(request.cookies.get("refresh_token"), db)

    if not auth_header and session_id.startswith("user:"):
        auth_header = _issue_auth_from_user_id(session_id.split(":", 1)[1], db)

    logger.info("/agent/chat/stream auth received: %s", "present" if auth_header else "missing")

    return StreamingResponse(
        run_orchestrator_stream(query, session_id=session_id, auth_header=auth_header),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions")
async def list_sessions(limit: Optional[int] = Query(default=50, ge=1, le=100)):
    """List all saved chat sessions from the database for sidebar navigation."""
    sessions = await list_all_memory_sessions(limit=limit)
    return {
        "count": len(sessions),
        "sessions": sessions,
    }


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: Optional[int] = Query(default=50, ge=1, le=200)):
    """Retrieve chat history for a session."""
    raw_items = await get_session_history(session_id=session_id, limit=limit)
    messages = []
    for item in raw_items:
        role = getattr(item, "role", None) or (item.get("role") if isinstance(item, dict) else "assistant")
        if str(role).lower() not in {"user", "assistant"}:
            continue
        content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else "")
        if isinstance(content, list):
            content_str = "\n".join(
                c if isinstance(c, str) else getattr(c, "text", "") or str(c) for c in content
            )
        else:
            content_str = str(content)
        content_clean = content_str.strip()
        if content_clean:
            messages.append({
                "role": str(role).lower(),
                "content": content_clean,
            })

    return {
        "session_id": session_id,
        "count": len(messages),
        "messages": messages,
    }


@router.delete("/history/{session_id}")
async def delete_history(session_id: str):
    """Clear chat history for a session."""
    await clear_session(session_id=session_id)
    return {
        "session_id": session_id,
        "status": "cleared",
    }
