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

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError
from sqlmodel import Session
from pydantic import BaseModel, Field

from ppsc_agents import run_orchestrator
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
