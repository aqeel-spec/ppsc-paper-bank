from __future__ import annotations

import asyncio
import os
import json
from dataclasses import asdict
from typing import Any, AsyncIterator, Optional, cast

import async_timeout
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from sqlalchemy import func, or_, Column as SAColumn
from sqlmodel import Session, select, col

from agents import Agent, Runner, SQLiteSession, function_tool, Tool

from app.database import get_engine, get_session, ensure_ai_explanation_column
from app.models import MCQ

from ppsc_agents.agent_system import (
    SESSION_DB,
    handle_api_error,
    search_internet,
    get_current_model,
    paper_agent,
    mcq_agent,
    scraping_agent,
    study_agent,
)

router = APIRouter(prefix="/ai", tags=["AI"])


@function_tool
async def get_mcq_by_id(mcq_id: int) -> str:
    """Fetch a single MCQ from the DB by ID (used by the agent)."""
    with Session(get_engine()) as session:
        mcq = session.get(MCQ, mcq_id)
        if not mcq:
            return f"MCQ not found for id={mcq_id}."

        lines: list[str] = []
        lines.append(f"MCQ ID: {mcq.id}")
        lines.append(f"Question: {mcq.question_text}")
        lines.append("Options:")
        lines.append(f"A. {mcq.option_a}")
        lines.append(f"B. {mcq.option_b}")
        lines.append(f"C. {mcq.option_c}")
        lines.append(f"D. {mcq.option_d}")
        lines.append(f"Correct Answer: {mcq.correct_answer}")
        if mcq.explanation:
            lines.append(f"Explanation: {mcq.explanation}")
        return "\n".join(lines)


@function_tool
async def search_mcqs(query: str, limit: int = 5) -> str:
    """Search MCQs in the DB by text (question/options/explanation)."""
    query = (query or "").strip()
    if not query:
        return "Search query is empty."

    limit = max(1, min(int(limit or 5), 20))
    q = query.lower()

    with Session(get_engine()) as session:
        stmt = (
            select(MCQ)
            .where(
                or_(
                    func.lower(MCQ.question_text).like(f"%{q}%"),
                    func.lower(MCQ.option_a).like(f"%{q}%"),
                    func.lower(MCQ.option_b).like(f"%{q}%"),
                    func.lower(MCQ.option_c).like(f"%{q}%"),
                    func.lower(MCQ.option_d).like(f"%{q}%"),
                    func.lower(func.coalesce(MCQ.explanation, "")).like(f"%{q}%"),
                )
            )
            .order_by(col(MCQ.id).desc())
            .limit(limit)
        )
        results = session.exec(stmt).all()

    if not results:
        return f"No MCQs matched: '{query}'."

    out = [f"Found {len(results)} MCQs for '{query}':"]
    for mcq in results:
        q_text = (mcq.question_text or "").strip().replace("\n", " ")
        if len(q_text) > 180:
            q_text = q_text[:177] + "..."
        out.append(f"- ID {mcq.id}: {q_text}")
    return "\n".join(out)


class MCQChatSolveRequest(BaseModel):
    mcq_id: Optional[int] = Field(
        default=None,
        description="If provided, the assistant will fetch the MCQ from the database by ID.",
    )
    question_text: Optional[str] = Field(
        default=None,
        description="MCQ question text (required if mcq_id not provided).",
    )
    options: Optional[list[str]] = Field(
        default=None,
        description="List of options in order (A, B, C, D, ...).",
    )

    session_id: Optional[str] = Field(
        default=None,
        description="Optional session id for conversation memory.",
    )

    use_internet: bool = Field(
        default=True,
        description="Whether to use internet search tool (DuckDuckGo instant answers).",
    )


def _build_mcq_explainer_agent(*, use_internet: bool) -> Agent[None]:
    tools: list[Tool] = cast(list[Tool], [get_mcq_by_id])
    if use_internet:
        tools.append(search_internet)

    return Agent(
        name="MCQ Explainer",
        instructions=(
            "You explain and solve MCQs for PPSC preparation.\n\n"
            "Rules:\n"
            "- If mcq_id is provided, call get_mcq_by_id and solve that MCQ.\n"
            "- If needed, use search_internet to validate facts.\n"
            "- Be short, accurate, and exam-focused (no fluff).\n"
            "- Output professional Markdown with exactly these sections:\n"
            "  - '## Final Answer' then exactly: 'Final Answer: <option letter or option text>'\n"
            "  - '## Brief Reason' with 2–4 bullet points max\n"
            "  - '## Sources' ONLY if you used internet search (bullet list of URLs)\n"
        ),
        model=get_current_model(),
        tools=tools,
    )


def _build_general_chat_agent(*, use_internet: bool) -> Agent[None]:
    tools: list[Tool] = cast(list[Tool], [
        paper_agent.as_tool("paper_creator", "Create and manage custom practice papers/tests"),
        mcq_agent.as_tool("mcq_assistant", "Browse MCQs and categories"),
        scraping_agent.as_tool("scraping_agent", "Scrape MCQs from supported websites"),
        study_agent.as_tool("study_assistant", "Study help and explanations"),
        search_mcqs,
        get_mcq_by_id,
    ])
    if use_internet:
        tools.append(search_internet)

    return Agent(
        name="PPSC Chat",
        instructions=(
            "You are the main chat assistant for the PPSC Paper Bank system.\n"
            "You can: create papers, browse MCQs, search MCQs in the DB by keyword, explain questions, and start scraping.\n\n"
            "Routing rules:\n"
            "- Paper creation/management → use paper_creator tool\n"
            "- Browse categories / get MCQs → use mcq_assistant tool\n"
            "- Keyword search in the database → use search_mcqs tool\n"
            "- Specific ID lookup → use get_mcq_by_id tool\n"
            "- Scraping requests → use scraping_agent tool\n"
            "- Study advice/plans → use study_assistant tool\n\n"
            "Response rules:\n"
            "- Be concise and practical.\n"
            "- Use Markdown.\n"
            "- If user asks for a list, return IDs + short titles.\n"
        ),
        model=get_current_model(),
        tools=tools,
    )


async def _stream_text_as_deltas(text: str) -> AsyncIterator[str]:
    chunk_size = int((os.getenv("CACHE_STREAM_CHUNK", "32") or "32").strip())
    delay_ms = int((os.getenv("CACHE_STREAM_DELAY_MS", "12") or "12").strip())

    if chunk_size < 1:
        chunk_size = 32
    if delay_ms < 0:
        delay_ms = 0

    for i in range(0, len(text), chunk_size):
        yield _sse("delta", {"delta": text[i : i + chunk_size]})
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)


def _format_prompt(payload: MCQChatSolveRequest) -> str:
    if payload.mcq_id is not None:
        return (
            "Solve this MCQ by ID and explain briefly. "
            f"mcq_id={payload.mcq_id}."
        )

    if not payload.question_text:
        raise HTTPException(422, "Provide either mcq_id or question_text")

    prompt = payload.question_text.strip()

    if payload.options:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        prompt += "\nOptions:\n"
        for i, opt in enumerate(payload.options):
            letter = letters[i] if i < len(letters) else f"({i+1})"
            prompt += f"{letter}. {opt}\n"

    return prompt


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_text_delta(raw_event: Any) -> Optional[str]:
    """Best-effort extraction of text deltas from OpenAI Responses stream events."""

    # raw_event is usually a pydantic model (ResponseStreamEvent). Convert to dict.
    try:
        payload = raw_event.model_dump()  # type: ignore[attr-defined]
    except Exception:
        try:
            payload = asdict(raw_event)
        except Exception:
            if isinstance(raw_event, dict):
                payload = raw_event
            else:
                return None

    event_type = payload.get("type")

    # Common Responses API delta event
    if event_type in {"response.output_text.delta", "response.output_text.annotation.added"}:
        delta = payload.get("delta")
        if isinstance(delta, str) and delta:
            return delta

    # Some providers may use different keys
    if event_type in {"response.output_text", "output_text.delta", "text.delta"}:
        delta = payload.get("delta") or payload.get("text")
        if isinstance(delta, str) and delta:
            return delta

    return None


@router.post("/chat")
async def chat_solve(payload: MCQChatSolveRequest, db: Session = Depends(get_session)):
    """Main chat endpoint (papers + tools + MCQ search)."""

    solver = _build_general_chat_agent(use_internet=payload.use_internet)
    prompt = _format_prompt(payload)

    memory_session = SQLiteSession(payload.session_id, SESSION_DB) if payload.session_id else None

    try:
        result = await Runner.run(solver, prompt, session=memory_session)

        return JSONResponse(
            {
                "session_id": payload.session_id,
                "mode": "chat",
                "output": result.final_output,
            }
        )
    except Exception as e:
        handle_api_error(e)

        msg = str(e)
        lowered = msg.lower()
        if any(term in lowered for term in ["rate limit", "quota", "resource_exhausted", "insufficient_quota", "429"]):
            raise HTTPException(
                status_code=429,
                detail=(
                    "LLM quota/rate limit reached. "
                    "Ensure GITHUB_TOKEN is valid and has sufficient quota for GitHub Models."
                ),
            )

        raise


@router.post("/chat/stream")
async def chat_solve_stream(payload: MCQChatSolveRequest, db: Session = Depends(get_session)):
    """Streaming MCQ explanation via Server-Sent Events (SSE)."""

    solver = _build_mcq_explainer_agent(use_internet=payload.use_internet)
    prompt = _format_prompt(payload)

    memory_session = SQLiteSession(payload.session_id, SESSION_DB) if payload.session_id else None

    async def gen() -> AsyncIterator[str]:
        current_solver = solver
        # initial meta
        yield _sse(
            "meta",
            {
                "session_id": payload.session_id,
                "use_internet": payload.use_internet,
            },
        )

        # Cache hit: stream cached text to preserve "AI is working" UX
        if payload.mcq_id is not None:
            mcq = db.get(MCQ, payload.mcq_id)
            if mcq and mcq.ai_explanation:
                yield _sse(
                    "status",
                    {
                        "message": "Serving cached AI explanation.",
                        "cached": True,
                        "source": "db",
                    },
                )
                async for chunk in _stream_text_as_deltas(mcq.ai_explanation):
                    yield chunk
                yield _sse("done", {"output": mcq.ai_explanation, "cached": True})
                return
            if mcq is None:
                yield _sse(
                    "status",
                    {
                        "message": "No MCQ found for mcq_id; cannot read/write ai_explanation.",
                        "mcq_id": payload.mcq_id,
                        "cached": False,
                    },
                )
                yield _sse(
                    "error",
                    {
                        "message": "mcq_id not found. Provide a valid mcq_id for streaming MCQ explanation.",
                    },
                )
                return
        else:
            yield _sse(
                "error",
                {
                    "message": "Streaming endpoint is for MCQ explanation. Provide mcq_id.",
                },
            )
            return

        # Run the streamed agent
        try:
            streamed = Runner.run_streamed(current_solver, prompt, session=memory_session)

            # Prevent silent hangs when the provider fails mid-stream.
            async with async_timeout.timeout(120):
                async for event in streamed.stream_events():
                    # Raw model deltas
                    if getattr(event, "type", None) == "raw_response_event":
                        delta = _extract_text_delta(getattr(event, "data", None))
                        if delta:
                            yield _sse("delta", {"delta": delta})
                        continue

            # completion
            if payload.mcq_id is not None:
                saved_to_cache = False
                mcq = db.get(MCQ, payload.mcq_id)
                if mcq:
                    mcq.ai_explanation = streamed.final_output
                    db.add(mcq)
                    try:
                        db.commit()
                        saved_to_cache = True
                    except Exception as commit_exc:
                        msg = str(commit_exc).lower()
                        if "ai_explanation" in msg and ("no such column" in msg or "unknown column" in msg or "invalid column" in msg):
                            ensure_ai_explanation_column()
                            db.commit()
                            saved_to_cache = True
                        else:
                            raise

                yield _sse(
                    "status",
                    {
                        "message": "Saved AI explanation to DB.",
                        "saved_to_cache": saved_to_cache,
                    },
                )

            yield _sse(
                "done",
                {
                    "output": streamed.final_output,
                    "cached": False,
                    "saved_to_cache": saved_to_cache if payload.mcq_id is not None else False,
                },
            )
            return

        except asyncio.TimeoutError:
            yield _sse(
                "error",
                {
                    "message": "Timed out while waiting for model stream (likely rate limit or provider outage).",
                },
            )
            return
        except Exception as e:
            handle_api_error(e)
            yield _sse(
                "error",
                {
                    "message": str(e),
                },
            )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class RoadmapRequest(BaseModel):
    weeks: int = Field(default=8, ge=1, le=52, description="How many weeks to plan")
    daily_hours: float = Field(default=2.0, ge=0.5, le=12, description="Avg study hours per day")
    target: str = Field(default="PPSC", description="Target exam")
    subjects: Optional[list[str]] = Field(default=None, description="Optional subject list")


@router.post("/roadmap")
async def roadmap(payload: RoadmapRequest):
    """Generate a visual-friendly PPSC preparation roadmap (emoji + Mermaid + animation hints)."""

    agent = Agent(
        name="PPSC Roadmap Designer",
        model=get_current_model(),
        instructions=(
            "Create a PPSC preparation roadmap that is visually engaging.\n"
            "The user wants emoji, visual structure, and frontend-friendly animation ideas.\n\n"
            "Output ONLY Markdown. Include:\n"
            "1) A short overview with emojis\n"
            "2) A week-by-week plan (weeks 1..N)\n"
            "3) A Mermaid diagram (flowchart or timeline)\n"
            "4) A short 'Animation Ideas' section describing simple UI animations (fade-in, progress bar, timeline reveal)\n\n"
            "Keep it practical and not too long."
        ),
    )

    subjects = payload.subjects or []
    subject_line = ", ".join(subjects) if subjects else "(not specified)"
    prompt = (
        f"Target: {payload.target}\n"
        f"Weeks: {payload.weeks}\n"
        f"Daily hours: {payload.daily_hours}\n"
        f"Subjects: {subject_line}\n"
    )

    result = await Runner.run(agent, prompt)
    return {"markdown": result.final_output}
