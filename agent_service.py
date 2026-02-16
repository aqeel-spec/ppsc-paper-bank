"""Agent HTTP Service.

This exposes the agent/orchestrator over HTTP so a frontend (e.g., Next.js)
can call it using a stable base URL.

Run locally:
  poetry run uvicorn agent_service:app --host 127.0.0.1 --port 8011 --reload

Then set:
  AGENT_SERVICE_BASE_URL=http://127.0.0.1:8011
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from ppsc_agents import run_orchestrator


app = FastAPI(title="PPSC Agent Service", version="1.0")


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


@app.get("/agent/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "offline": "1" if os.getenv("PPSC_OFFLINE") == "1" else "0",
    }


@app.post("/agent/chat", response_model=AgentChatResponse)
async def agent_chat(payload: AgentChatRequest) -> AgentChatResponse:
    # Session policy: if none is provided, create a lightweight one.
    # (Frontend should ideally generate + persist a session_id cookie.)
    session_id = payload.session_id or "anon"

    answer = await run_orchestrator(
        payload.query,
        session_id=session_id,
    )

    return AgentChatResponse(session_id=session_id, answer=answer)
