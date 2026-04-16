"""Agent HTTP Service.

This exposes the agent/orchestrator over HTTP so a frontend (e.g., Next.js)
can call it using a stable base URL.

Run locally:
    uv run uvicorn agent_service:app --host 127.0.0.1 --port 8011 --reload

Then set:
  AGENT_SERVICE_BASE_URL=http://127.0.0.1:8011
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from jose import JWTError
from sqlmodel import Session
from pydantic import BaseModel, Field

from ppsc_agents import run_orchestrator
from app.models.user import User
from app.database import get_session
from app.security import create_access_token, decode_token, get_optional_user
from fastapi import Depends


app = FastAPI(title="PPSC Agent Service", version="1.0")
logger = logging.getLogger(__name__)


class AgentChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User message")
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


@app.get("/agent/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "offline": "1" if os.getenv("PPSC_OFFLINE") == "1" else "0",
    }


@app.post("/agent/chat", response_model=AgentChatResponse)
async def agent_chat(
    payload: AgentChatRequest,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_session),
) -> AgentChatResponse:
    # Session policy: if none is provided, create a lightweight one.
    # (Frontend should ideally generate + persist a session_id cookie.)
    session_id = payload.session_id or "anon"

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

    logger.info("/agent/chat auth received: %s", "present" if auth_header else "missing")
    answer = await run_orchestrator(
        payload.query,
        session_id=session_id,
        auth_header=auth_header,
    )

    return AgentChatResponse(session_id=session_id, answer=answer)
