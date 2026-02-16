"""Agent HTTP routes.

These routes expose the multi-tool orchestrator (papers, MCQs, scraping, study)
over HTTP from the main API server.

This duplicates the functionality of the standalone `agent_service.py`, but as a
router so you can run everything in one process.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ppsc_agents import run_orchestrator


router = APIRouter(prefix="/agent", tags=["Agent"])


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


@router.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "offline": "1" if os.getenv("PPSC_OFFLINE") == "1" else "0",
    }


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(payload: AgentChatRequest) -> AgentChatResponse:
    session_id = payload.session_id or "anon"
    answer = await run_orchestrator(payload.query, session_id=session_id)
    return AgentChatResponse(session_id=session_id, answer=answer)
