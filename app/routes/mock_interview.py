"""
Mock Interview Panel API — AI-powered PPSC interview simulation.

Uses the existing GitHub Models (OpenAI-compatible) LLM backend via LiteLLM.
Four specialist interviewer avatars + a panel orchestrator.
All sessions, messages, and feedback are persisted to the main database.

Endpoints
---------
POST   /interview/start              → start a new interview session
POST   /interview/chat               → continue an interview conversation
POST   /interview/chat/stream        → continue (SSE streamed)
POST   /interview/panel              → full panel interview (4 interviewers rotate)
POST   /interview/feedback           → AI feedback report for a session
GET    /interview/avatars            → list available interviewer avatars
GET    /interview/sessions           → list all sessions (paginated)
GET    /interview/sessions/{id}      → full session detail (messages + feedback)
PATCH  /interview/sessions/{id}      → update session status (complete / abandon)
DELETE /interview/session/{id}       → clear a session
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
import logging
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, List, Optional, cast

import async_timeout
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select, col

from agents import Agent, Runner, SQLiteSession, Tool

from app.database import get_session
from app.models.interview import (
    InterviewFeedback,
    InterviewMessage,
    InterviewSession,
    InterviewQuestionScore,
    InterviewSessionRead,
    InterviewSessionDetail,
    InterviewMessageRead,
    InterviewFeedbackRead,
    InterviewQuestionScoreRead,
    InterviewMode,
    MessageRole,
    SessionStatus,
)
from ppsc_agents.agent_system import (
    SESSION_DB,
    get_current_model,
    handle_api_error,
    search_internet,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interview", tags=["Mock Interview"])


# ── Avatar definitions ─────────────────────────────────────────────────────

class AvatarType(str, Enum):
    general_knowledge = "general_knowledge"
    english = "english"
    behavioral = "behavioral"
    subject_expert = "subject_expert"


_AVATAR_META: dict[AvatarType, dict[str, str]] = {
    AvatarType.general_knowledge: {
        "name": "Dr. Asif Khan",
        "title": "General Knowledge Expert",
        "emoji": "🌍",
        "description": "Tests current affairs, Pakistan studies, geography, history, and everyday general knowledge.",
    },
    AvatarType.english: {
        "name": "Prof. Sarah Ahmed",
        "title": "English & Communication Specialist",
        "emoji": "📝",
        "description": "Evaluates grammar, vocabulary, comprehension, and communication skills.",
    },
    AvatarType.behavioral: {
        "name": "Ms. Fatima Noor",
        "title": "Behavioral & HR Interviewer",
        "emoji": "🤝",
        "description": "Assesses personality, ethics, situational judgment, and public-service motivation.",
    },
    AvatarType.subject_expert: {
        "name": "Dr. Usman Tariq",
        "title": "Subject Matter Expert",
        "emoji": "🎓",
        "description": "Deep-dives into the candidate's applied subject (CS, Law, Admin, etc.).",
    },
}

# ── Structured interview: avatar rotation order ────────────────────────────

STRUCTURED_AVATAR_ORDER: list[AvatarType] = [
    AvatarType.general_knowledge,
    AvatarType.english,
    AvatarType.subject_expert,
    AvatarType.behavioral,
]


# ── System prompts ─────────────────────────────────────────────────────────

def _avatar_system_prompt(avatar: AvatarType, subject: str | None = None) -> str:
    meta = _AVATAR_META[avatar]
    base = (
        f"You are **{meta['name']}**, a {meta['title']} on a PPSC mock interview panel.\n\n"
        "Rules you MUST follow:\n"
        "1. You are conducting a **realistic PPSC interview** — be professional but encouraging.\n"
        "2. Ask ONE question at a time, then wait for the candidate's answer.\n"
        "3. After the candidate answers, give brief feedback (1-2 sentences) and then ask the next question.\n"
        "4. Keep track of how many questions you have asked in this session.\n"
        "5. After 5 questions, wrap up your portion with a short summary of the candidate's performance.\n"
        "6. Grade each answer internally: Excellent / Good / Needs Improvement.\n"
        "7. Be warm and constructive — this is for student practice, not to intimidate.\n"
        "8. Use simple, clear language. Format in Markdown.\n\n"
    )
    if avatar == AvatarType.general_knowledge:
        base += (
            "Focus areas: Current affairs (Pakistan & world), Pakistan Studies, "
            "geography, history, basic science, everyday GK.\n"
            "Start with an easier question and gradually increase difficulty.\n"
        )
    elif avatar == AvatarType.english:
        base += (
            "Focus areas: Grammar, vocabulary, sentence correction, comprehension, "
            "idioms/phrases, and verbal reasoning.\n"
            "You may present a short passage or sentence and ask for corrections or explanations.\n"
        )
    elif avatar == AvatarType.behavioral:
        base += (
            "Focus areas: Motivation for public service, ethical dilemmas, "
            "situational judgment, teamwork, leadership, and stress management.\n"
            "Use the STAR method to evaluate answers (Situation, Task, Action, Result).\n"
        )
    elif avatar == AvatarType.subject_expert:
        subj = subject or "the candidate's applied subject"
        base += (
            f"Focus area: **{subj}**\n"
            "Ask technical / conceptual questions relevant to this subject at PPSC exam level.\n"
            "Start with fundamentals and progress to applied / analytical questions.\n"
        )
    return base


def _panel_system_prompt(subject: str | None = None) -> str:
    subj = subject or "General"
    return (
        "You are the **Chairperson** of a PPSC mock interview panel.\n\n"
        "Your panel has four members:\n"
        "1. 🌍 Dr. Asif Khan — General Knowledge Expert\n"
        "2. 📝 Prof. Sarah Ahmed — English & Communication Specialist\n"
        "3. 🤝 Ms. Fatima Noor — Behavioral & HR Interviewer\n"
        f"4. 🎓 Dr. Usman Tariq — Subject Expert ({subj})\n\n"
        "Conduct the interview as follows:\n"
        "- Introduce the panel briefly at the start.\n"
        "- Each panelist asks 2-3 questions in rotation.\n"
        "- After each candidate answer, the current panelist gives brief feedback.\n"
        "- After all panelists finish, you (the Chairperson) provide a consolidated score card.\n"
        "- Score card format: table with panelist name, area, score out of 10, and remarks.\n"
        "- Ask ONE question at a time, wait for the candidate's response.\n"
        "- Be professional, encouraging, and realistic.\n"
        "- Use Markdown formatting.\n"
    )


def _feedback_system_prompt() -> str:
    return (
        "You are an interview performance analyst.\n"
        "Given the full conversation history of a PPSC mock interview, produce a detailed feedback report.\n\n"
        "Output MUST be Markdown with these sections:\n"
        "## Overall Score\n"
        "A score out of 100 with a one-line verdict.\n\n"
        "## Category Scores\n"
        "A table: | Category | Score /10 | Remarks |\n\n"
        "## Strengths\n"
        "Bullet list of 3-5 strengths.\n\n"
        "## Areas for Improvement\n"
        "Bullet list of 3-5 areas to work on.\n\n"
        "## Recommended Study Plan\n"
        "A short 1-week study plan targeting the weak areas.\n\n"
        "Be constructive, specific, and encouraging.\n"
    )


# ── Structured interview prompts ──────────────────────────────────────────

def _structured_question_prompt(
    avatar: AvatarType,
    question_number: int,
    total_for_avatar: int,
    subject: str | None = None,
    previous_questions: list[str] | None = None,
) -> str:
    """Build a prompt that asks the AI to generate exactly ONE question."""
    meta = _AVATAR_META[avatar]
    prev_section = ""
    if previous_questions:
        prev_list = "\n".join(f"  - {q}" for q in previous_questions)
        prev_section = (
            f"\n\nPrevious questions you have already asked "
            f"(do NOT repeat any of these):\n{prev_list}\n"
        )

    subj_note = ""
    if avatar == AvatarType.subject_expert and subject:
        subj_note = f"\nSubject specialization: **{subject}**\n"

    difficulty = "easy" if question_number == 1 else ("medium" if question_number == 2 else "hard")

    return (
        f"You are **{meta['name']}**, a {meta['title']} on a PPSC mock interview panel.\n"
        f"This is question {question_number} of {total_for_avatar} from your section.\n"
        f"Difficulty level: **{difficulty}** (increase difficulty progressively).\n"
        f"{subj_note}{prev_section}\n"
        "Generate **exactly ONE** clear, concise interview question.\n"
        "Output ONLY the question text — no greetings, no numbering, no commentary.\n"
        "The question should be appropriate for a PPSC competitive exam interview.\n"
    )


def _structured_scoring_prompt(
    avatar: AvatarType,
    question: str,
    answer: str,
    subject: str | None = None,
) -> str:
    """Build a prompt that asks the AI to score a candidate answer 0-100."""
    meta = _AVATAR_META[avatar]
    subj_note = f" (Subject: {subject})" if subject else ""
    return (
        f"You are **{meta['name']}**, a {meta['title']}{subj_note} on a PPSC interview panel.\n\n"
        "Score the candidate's answer on a scale of **0 to 100** using this rubric:\n"
        "- **0-20**: Completely wrong / no relevant content\n"
        "- **21-40**: Major gaps, only partially addresses the question\n"
        "- **41-60**: Acceptable but lacks depth or accuracy\n"
        "- **61-80**: Good answer with solid understanding\n"
        "- **81-100**: Excellent, comprehensive, and well-articulated\n\n"
        f"**Question:** {question}\n\n"
        f"**Candidate's Answer:** {answer}\n\n"
        "Respond in this EXACT JSON format (no markdown fencing, no extra text):\n"
        '{"score": <number 0-100>, "feedback": "<2-3 sentence constructive feedback>"}\n'
    )


def _structured_final_report_prompt(
    scores_by_avatar: dict[str, list[dict]],
    candidate_name: str | None = None,
    subject: str | None = None,
) -> str:
    """Build a prompt for the final consolidated interview report."""
    name = candidate_name or "The candidate"
    subj = subject or "General"

    score_sections = []
    for avatar_key, scores in scores_by_avatar.items():
        meta = _AVATAR_META.get(AvatarType(avatar_key), {})
        avatar_name = meta.get("name", avatar_key)
        avatar_emoji = meta.get("emoji", "")
        lines = []
        for s in scores:
            lines.append(
                f"  Q: {s['question'][:80]}...\n"
                f"  A: {s['answer'][:80]}...\n"
                f"  Score: {s['score']}/100 — {s['feedback']}"
            )
        score_sections.append(
            f"### {avatar_emoji} {avatar_name}\n" + "\n\n".join(lines)
        )

    all_scores = "\n\n".join(score_sections)

    return (
        "You are a senior PPSC interview performance analyst.\n"
        f"Candidate: **{name}** | Subject: **{subj}**\n\n"
        "Here are all the per-question scores from the panel:\n\n"
        f"{all_scores}\n\n"
        "---\n\n"
        "Produce a comprehensive **Final Interview Report** in Markdown with:\n\n"
        "## Overall Score\n"
        "Compute a weighted overall score out of 100 (average of all question scores) "
        "and give a one-line verdict (Outstanding / Very Good / Good / Needs Improvement / Poor).\n\n"
        "## Avatar-wise Score Card\n"
        "| Interviewer | Area | Avg Score /100 | Remarks |\n"
        "Fill this table for each interviewer.\n\n"
        "## Strengths\n"
        "3-5 bullet points of strengths observed.\n\n"
        "## Areas for Improvement\n"
        "3-5 bullet points with specific advice.\n\n"
        "## Recommended Study Plan\n"
        "A 1-week study plan targeting weak areas.\n\n"
        "Be constructive, specific, and encouraging. Use Markdown formatting.\n"
    )


# ── Request / Response schemas ─────────────────────────────────────────────

class InterviewStartRequest(BaseModel):
    avatar: AvatarType = Field(
        default=AvatarType.general_knowledge,
        description="Which interviewer avatar to use.",
    )
    subject: Optional[str] = Field(
        default=None,
        description="Subject specialization (relevant for subject_expert avatar).",
        examples=["Computer Science", "Law", "Public Administration"],
    )
    candidate_name: Optional[str] = Field(
        default=None,
        description="Candidate's name for personalized experience.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Provide to resume an existing session, or leave empty for a new one.",
    )


class InterviewChatRequest(BaseModel):
    session_id: str = Field(..., description="Session ID returned from /start.")
    message: str = Field(..., min_length=1, max_length=5000, description="Candidate's response or message.")
    avatar: AvatarType = Field(
        default=AvatarType.general_knowledge,
        description="Which avatar is interviewing.",
    )
    subject: Optional[str] = Field(default=None, description="Subject (for subject_expert).")


class PanelInterviewRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Provide to resume, or empty for new.")
    message: str = Field(..., min_length=1, max_length=5000, description="Candidate's message.")
    subject: Optional[str] = Field(
        default=None,
        description="Subject for the subject expert panelist.",
        examples=["Computer Science"],
    )
    candidate_name: Optional[str] = Field(default=None)


class FeedbackRequest(BaseModel):
    session_id: str = Field(..., description="Session ID to generate feedback for.")


class SessionUpdateRequest(BaseModel):
    status: str = Field(
        ...,
        description="New status: 'completed' or 'abandoned'.",
        examples=["completed", "abandoned"],
    )


class InterviewResponse(BaseModel):
    session_id: str
    avatar: str
    avatar_name: str
    avatar_emoji: str
    response: str
    message_count: int = 0


class FeedbackResponse(BaseModel):
    session_id: str
    feedback: str
    overall_score: Optional[int] = None


# ── Structured interview request / response schemas ────────────────────────

class StructuredStartRequest(BaseModel):
    candidate_name: Optional[str] = Field(
        default=None, description="Candidate's name for personalized experience.",
    )
    subject: Optional[str] = Field(
        default=None,
        description="Subject specialization for the Subject Expert avatar.",
        examples=["Computer Science", "Law", "Public Administration"],
    )
    questions_per_avatar: int = Field(
        default=3, ge=1, le=10,
        description="Number of questions each of the 4 avatars will ask (default 3 → 12 total).",
    )


class StructuredStartResponse(BaseModel):
    session_id: str
    candidate_name: Optional[str] = None
    subject: Optional[str] = None
    questions_per_avatar: int
    total_questions: int
    avatar_order: list[dict[str, Any]]
    message: str


class GetQuestionResponse(BaseModel):
    session_id: str
    question_index: int
    total_questions: int
    avatar_id: str
    avatar_name: str
    avatar_emoji: str
    avatar_title: str
    question_number_for_avatar: int
    questions_per_avatar: int
    question_text: str
    is_last_question: bool


class SubmitAnswerRequest(BaseModel):
    session_id: str = Field(..., description="Session ID from /structured/start.")
    answer: str = Field(
        ..., min_length=1, max_length=10000,
        description="Candidate's answer to the current question.",
    )


class SubmitAnswerResponse(BaseModel):
    session_id: str
    question_index: int
    avatar_id: str
    avatar_name: str
    avatar_emoji: str
    question_text: str
    answer_text: str
    score: float
    ai_feedback: str
    is_interview_complete: bool
    next_avatar_id: Optional[str] = None
    next_avatar_name: Optional[str] = None
    progress: str


class FinishInterviewResponse(BaseModel):
    session_id: str
    candidate_name: Optional[str] = None
    subject: Optional[str] = None
    total_questions_answered: int
    overall_score: float
    avatar_scores: list[dict]
    detailed_report: str
    question_scores: list[dict]


# ── Agent builders ─────────────────────────────────────────────────────────

def _build_interview_agent(
    avatar: AvatarType,
    subject: str | None = None,
    use_internet: bool = False,
) -> Agent[None]:
    tools: list[Tool] = []
    if use_internet:
        tools = cast(list[Tool], [search_internet])
    return Agent(
        name=_AVATAR_META[avatar]["name"],
        instructions=_avatar_system_prompt(avatar, subject),
        model=get_current_model(),
        tools=tools,
    )


def _build_panel_agent(subject: str | None = None) -> Agent[None]:
    tools: list[Tool] = cast(list[Tool], [search_internet])
    return Agent(
        name="PPSC Panel Chairperson",
        instructions=_panel_system_prompt(subject),
        model=get_current_model(),
        tools=tools,
    )


def _build_feedback_agent() -> Agent[None]:
    return Agent(
        name="Performance Analyst",
        instructions=_feedback_system_prompt(),
        model=get_current_model(),
    )


# ── DB helper functions ───────────────────────────────────────────────────

def _get_or_create_session(
    db: Session,
    session_id: str,
    avatar: str,
    mode: str = InterviewMode.single.value,
    candidate_name: str | None = None,
    subject: str | None = None,
) -> InterviewSession:
    """Fetch existing DB session or create a new one."""
    stmt = select(InterviewSession).where(InterviewSession.session_id == session_id)
    db_session = db.exec(stmt).first()
    if db_session:
        return db_session
    db_session = InterviewSession(
        session_id=session_id,
        avatar=avatar,
        mode=mode,
        candidate_name=candidate_name,
        subject=subject,
        status=SessionStatus.active.value,
        total_messages=0,
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    logger.info(f"📝 DB: Created interview session {session_id}")
    return db_session


def _log_message(
    db: Session,
    db_session: InterviewSession,
    role: str,
    content: str,
    avatar: str | None = None,
) -> InterviewMessage:
    """Persist a single message and bump session counter."""
    msg = InterviewMessage(
        session_id=db_session.session_id,
        role=role,
        avatar=avatar,
        content=content,
        message_index=db_session.total_messages,
    )
    db.add(msg)
    db_session.total_messages += 1
    db.add(db_session)
    db.commit()
    db.refresh(msg)
    return msg


def _log_feedback(
    db: Session,
    session_id: str,
    feedback_text: str,
) -> InterviewFeedback:
    """Persist a feedback report and try to extract overall score."""
    score = _extract_score(feedback_text)
    fb = InterviewFeedback(
        session_id=session_id,
        feedback=feedback_text,
        overall_score=score,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def _extract_score(text: str) -> int | None:
    """Try to extract an overall score (0-100) from feedback markdown."""
    patterns = [
        r"overall\s*score[:\s]*\**(\d{1,3})\**\s*/\s*100",
        r"(\d{1,3})\s*/\s*100",
        r"(\d{1,3})\s+out\s+of\s+100",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 0 <= val <= 100:
                return val
    return None


# ── SSE helper ─────────────────────────────────────────────────────────────

def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/avatars", summary="List available interviewer avatars")
async def list_avatars():
    """Return metadata for all available interviewer avatars."""
    return [
        {
            "id": av.value,
            "name": meta["name"],
            "title": meta["title"],
            "emoji": meta["emoji"],
            "description": meta["description"],
        }
        for av, meta in _AVATAR_META.items()
    ]


# ── POST /start ────────────────────────────────────────────────────────────

@router.post("/start", summary="Start a new interview session", response_model=InterviewResponse)
async def start_interview(
    payload: InterviewStartRequest,
    db: Session = Depends(get_session),
):
    session_id = payload.session_id or f"interview_{uuid.uuid4().hex[:12]}"
    meta = _AVATAR_META[payload.avatar]

    # ── DB: create session row ──
    db_session = _get_or_create_session(
        db,
        session_id=session_id,
        avatar=payload.avatar.value,
        mode=InterviewMode.single.value,
        candidate_name=payload.candidate_name,
        subject=payload.subject,
    )

    agent = _build_interview_agent(payload.avatar, payload.subject)

    name_part = f" The candidate's name is {payload.candidate_name}." if payload.candidate_name else ""
    subject_part = f" Subject: {payload.subject}." if payload.subject else ""
    opening = (
        f"Start the interview.{name_part}{subject_part} "
        "Introduce yourself briefly and ask the first question."
    )

    llm_session = SQLiteSession(session_id, SESSION_DB)

    try:
        result = await Runner.run(agent, opening, session=llm_session)
        logger.info(f"🎙️ Interview started — session={session_id}, avatar={payload.avatar.value}")
    except Exception as e:
        handle_api_error(e)
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)[:200]}")

    # ── DB: log system opening + interviewer response ──
    _log_message(db, db_session, MessageRole.system.value, opening)
    _log_message(db, db_session, MessageRole.interviewer.value, result.final_output, avatar=payload.avatar.value)

    return InterviewResponse(
        session_id=session_id,
        avatar=payload.avatar.value,
        avatar_name=meta["name"],
        avatar_emoji=meta["emoji"],
        response=result.final_output,
        message_count=db_session.total_messages,
    )


# ── POST /chat ─────────────────────────────────────────────────────────────

@router.post("/chat", summary="Continue interview conversation", response_model=InterviewResponse)
async def interview_chat(
    payload: InterviewChatRequest,
    db: Session = Depends(get_session),
):
    meta = _AVATAR_META[payload.avatar]

    # ── DB: get or create session ──
    db_session = _get_or_create_session(
        db,
        session_id=payload.session_id,
        avatar=payload.avatar.value,
    )

    agent = _build_interview_agent(payload.avatar, payload.subject)
    llm_session = SQLiteSession(payload.session_id, SESSION_DB)

    try:
        result = await Runner.run(agent, payload.message, session=llm_session)
        logger.info(f"💬 Interview chat — session={payload.session_id}")
    except Exception as e:
        handle_api_error(e)
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)[:200]}")

    # ── DB: log candidate message + interviewer response ──
    _log_message(db, db_session, MessageRole.candidate.value, payload.message)
    _log_message(db, db_session, MessageRole.interviewer.value, result.final_output, avatar=payload.avatar.value)

    return InterviewResponse(
        session_id=payload.session_id,
        avatar=payload.avatar.value,
        avatar_name=meta["name"],
        avatar_emoji=meta["emoji"],
        response=result.final_output,
        message_count=db_session.total_messages,
    )


# ── POST /chat/stream ─────────────────────────────────────────────────────

@router.post(
    "/chat/stream",
    summary="Continue interview (SSE stream)",
    response_class=StreamingResponse,
)
async def interview_chat_stream(
    payload: InterviewChatRequest,
    db: Session = Depends(get_session),
):
    meta = _AVATAR_META[payload.avatar]

    # ── DB: get or create session ──
    db_session = _get_or_create_session(
        db,
        session_id=payload.session_id,
        avatar=payload.avatar.value,
    )

    # Log candidate message immediately
    _log_message(db, db_session, MessageRole.candidate.value, payload.message)

    agent = _build_interview_agent(payload.avatar, payload.subject)
    llm_session = SQLiteSession(payload.session_id, SESSION_DB)

    async def gen() -> AsyncIterator[str]:
        yield _sse("meta", {
            "session_id": payload.session_id,
            "avatar": payload.avatar.value,
            "avatar_name": meta["name"],
            "avatar_emoji": meta["emoji"],
        })

        collected_output = ""

        try:
            streamed = Runner.run_streamed(agent, payload.message, session=llm_session)

            async with async_timeout.timeout(120):
                async for event in streamed.stream_events():
                    if getattr(event, "type", None) == "raw_response_event":
                        data = getattr(event, "data", None)
                        if data:
                            try:
                                payload_dict = data.model_dump()
                            except Exception:
                                payload_dict = data if isinstance(data, dict) else {}
                            delta = payload_dict.get("delta")
                            if isinstance(delta, str) and delta:
                                collected_output += delta
                                yield _sse("delta", {"delta": delta})

            final = streamed.final_output or collected_output
            yield _sse("done", {"output": final})

            # ── DB: log interviewer response ──
            if final:
                _log_message(
                    db, db_session,
                    MessageRole.interviewer.value,
                    final,
                    avatar=payload.avatar.value,
                )

        except asyncio.TimeoutError:
            yield _sse("error", {"message": "Interview response timed out."})
        except Exception as e:
            handle_api_error(e)
            yield _sse("error", {"message": str(e)[:300]})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── POST /panel ────────────────────────────────────────────────────────────

@router.post("/panel", summary="Full panel interview (all 4 avatars)", response_model=InterviewResponse)
async def panel_interview(
    payload: PanelInterviewRequest,
    db: Session = Depends(get_session),
):
    session_id = payload.session_id or f"panel_{uuid.uuid4().hex[:12]}"

    # ── DB: create session ──
    db_session = _get_or_create_session(
        db,
        session_id=session_id,
        avatar="panel",
        mode=InterviewMode.panel.value,
        candidate_name=payload.candidate_name,
        subject=payload.subject,
    )

    agent = _build_panel_agent(payload.subject)
    llm_session = SQLiteSession(session_id, SESSION_DB)

    msg = payload.message
    if not payload.session_id:
        name_part = f" Candidate: {payload.candidate_name}." if payload.candidate_name else ""
        subject_part = f" Subject specialization: {payload.subject}." if payload.subject else ""
        msg = (
            f"Begin the panel interview.{name_part}{subject_part} "
            "Introduce the panel and start with the first panelist's question."
        )

    try:
        result = await Runner.run(agent, msg, session=llm_session)
        logger.info(f"🎙️ Panel interview — session={session_id}")
    except Exception as e:
        handle_api_error(e)
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)[:200]}")

    # ── DB: log messages ──
    _log_message(db, db_session, MessageRole.candidate.value, payload.message)
    _log_message(db, db_session, MessageRole.interviewer.value, result.final_output, avatar="panel")

    return InterviewResponse(
        session_id=session_id,
        avatar="panel",
        avatar_name="PPSC Panel",
        avatar_emoji="👥",
        response=result.final_output,
        message_count=db_session.total_messages,
    )


# ── POST /feedback ─────────────────────────────────────────────────────────

@router.post("/feedback", summary="Get performance feedback for a session", response_model=FeedbackResponse)
async def get_feedback(
    payload: FeedbackRequest,
    db: Session = Depends(get_session),
):
    llm_session = SQLiteSession(payload.session_id, SESSION_DB)
    items = await llm_session.get_items()

    if not items:
        raise HTTPException(
            status_code=404,
            detail=f"No conversation found for session '{payload.session_id}'.",
        )

    # Build transcript from session history
    transcript_lines: list[str] = []
    for item in items:
        entry: Any = item
        role: str = getattr(entry, "role", "unknown")
        raw: Any = getattr(entry, "content", None)
        if raw is None:
            continue
        if isinstance(raw, str):
            content = raw
        elif isinstance(raw, list):
            content = " ".join(
                (part.get("text", "") if isinstance(part, dict) else str(part))
                for part in raw
            )
        else:
            content = str(raw)
        if content:
            transcript_lines.append(f"**{role}**: {content}")

    transcript = "\n\n".join(transcript_lines)
    prompt = (
        "Here is the full transcript of a PPSC mock interview session.\n"
        "Analyze the candidate's performance and produce a detailed feedback report.\n\n"
        f"---\n\n{transcript}\n\n---"
    )

    agent = _build_feedback_agent()

    try:
        result = await Runner.run(agent, prompt)
        logger.info(f"📊 Feedback generated — session={payload.session_id}")
    except Exception as e:
        handle_api_error(e)
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)[:200]}")

    # ── DB: save feedback ──
    fb = _log_feedback(db, payload.session_id, result.final_output)

    # Mark session as completed
    stmt = select(InterviewSession).where(InterviewSession.session_id == payload.session_id)
    db_sess = db.exec(stmt).first()
    if db_sess:
        db_sess.status = SessionStatus.completed.value
        db_sess.ended_at = datetime.utcnow()
        db.add(db_sess)
        db.commit()

    return FeedbackResponse(
        session_id=payload.session_id,
        feedback=result.final_output,
        overall_score=fb.overall_score,
    )


# ── GET /sessions ──────────────────────────────────────────────────────────

@router.get(
    "/sessions",
    summary="List all interview sessions (paginated)",
    response_model=List[InterviewSessionRead],
)
async def list_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status: active, completed, abandoned"),
    avatar: Optional[str] = Query(None, description="Filter by avatar type"),
    db: Session = Depends(get_session),
):
    stmt = select(InterviewSession).order_by(col(InterviewSession.id).desc())
    if status:
        stmt = stmt.where(InterviewSession.status == status)
    if avatar:
        stmt = stmt.where(InterviewSession.avatar == avatar)
    stmt = stmt.offset(skip).limit(limit)
    sessions = db.exec(stmt).all()
    return sessions


# ── GET /sessions/{session_id} ─────────────────────────────────────────────

@router.get(
    "/sessions/{session_id}",
    summary="Get full session detail with messages and feedback",
    response_model=InterviewSessionDetail,
)
async def get_session_detail(
    session_id: str,
    db: Session = Depends(get_session),
):
    stmt = select(InterviewSession).where(InterviewSession.session_id == session_id)
    db_session = db.exec(stmt).first()
    if not db_session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    # Fetch messages
    msg_stmt = (
        select(InterviewMessage)
        .where(InterviewMessage.session_id == session_id)
        .order_by(col(InterviewMessage.message_index))
    )
    messages = db.exec(msg_stmt).all()

    # Fetch feedback
    fb_stmt = (
        select(InterviewFeedback)
        .where(InterviewFeedback.session_id == session_id)
        .order_by(col(InterviewFeedback.id).desc())
    )
    feedbacks = db.exec(fb_stmt).all()

    # Fetch question scores (structured interviews)
    qs_stmt = (
        select(InterviewQuestionScore)
        .where(InterviewQuestionScore.session_id == session_id)
        .order_by(col(InterviewQuestionScore.question_index))
    )
    q_scores = db.exec(qs_stmt).all()

    return InterviewSessionDetail(
        id=db_session.id,
        session_id=db_session.session_id,
        candidate_name=db_session.candidate_name,
        avatar=db_session.avatar,
        subject=db_session.subject,
        mode=db_session.mode,
        status=db_session.status,
        total_messages=db_session.total_messages,
        questions_per_avatar=db_session.questions_per_avatar,
        current_avatar_index=db_session.current_avatar_index,
        current_question_index=db_session.current_question_index,
        total_questions=db_session.total_questions,
        overall_score=db_session.overall_score,
        started_at=db_session.started_at,
        ended_at=db_session.ended_at,
        messages=[InterviewMessageRead.model_validate(m) for m in messages],
        feedbacks=[InterviewFeedbackRead.model_validate(f) for f in feedbacks],
        question_scores=[InterviewQuestionScoreRead.model_validate(q) for q in q_scores],
    )


# ── PATCH /sessions/{session_id} ───────────────────────────────────────────

@router.patch(
    "/sessions/{session_id}",
    summary="Update session status (complete or abandon)",
    response_model=InterviewSessionRead,
)
async def update_session_status(
    session_id: str,
    payload: SessionUpdateRequest,
    db: Session = Depends(get_session),
):
    if payload.status not in (SessionStatus.completed.value, SessionStatus.abandoned.value):
        raise HTTPException(
            status_code=400,
            detail="Status must be 'completed' or 'abandoned'.",
        )

    stmt = select(InterviewSession).where(InterviewSession.session_id == session_id)
    db_session = db.exec(stmt).first()
    if not db_session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    db_session.status = payload.status
    db_session.ended_at = datetime.utcnow()
    db.add(db_session)
    db.commit()
    db.refresh(db_session)

    logger.info(f"📋 Session {session_id} → {payload.status}")
    return db_session


# ── DELETE /session/{session_id} ───────────────────────────────────────────

@router.delete(
    "/session/{session_id}",
    summary="Clear an interview session (LLM memory + DB records)",
)
async def clear_interview_session(
    session_id: str,
    db: Session = Depends(get_session),
):
    # Clear LLM session memory
    llm_session = SQLiteSession(session_id, SESSION_DB)
    await llm_session.clear_session()

    # Delete DB records (order matters for FK constraints)
    for model_cls in (InterviewMessage, InterviewFeedback, InterviewQuestionScore, InterviewSession):
        stmt = select(model_cls).where(model_cls.session_id == session_id)  # type: ignore[arg-type]
        rows = db.exec(stmt).all()
        for row in rows:
            db.delete(row)
    db.commit()

    logger.info(f"🗑️ Cleared interview session: {session_id}")
    return {"status": "cleared", "session_id": session_id}


# ══════════════════════════════════════════════════════════════════════════
#   STRUCTURED INTERVIEW ENDPOINTS
#   Sequential avatar questioning with per-question AI scoring.
#   Flow: /structured/start → /structured/getQuestion (loop) →
#         /structured/submitAnswer (loop) → /structured/finishInterview
# ══════════════════════════════════════════════════════════════════════════


# ── POST /structured/start ─────────────────────────────────────────────────

@router.post(
    "/structured/start",
    summary="Start a structured interview session (sequential avatars, per-question scoring)",
    response_model=StructuredStartResponse,
)
async def structured_start(
    payload: StructuredStartRequest,
    db: Session = Depends(get_session),
):
    """
    Initialises a structured interview with 4 avatars in fixed rotation.
    Each avatar asks `questions_per_avatar` questions.  Total = 4 × questions_per_avatar.
    """
    session_id = f"struct_{uuid.uuid4().hex[:12]}"
    total_q = 4 * payload.questions_per_avatar

    db_session = InterviewSession(
        session_id=session_id,
        avatar="structured",
        mode=InterviewMode.structured.value,
        candidate_name=payload.candidate_name,
        subject=payload.subject,
        status=SessionStatus.active.value,
        total_messages=0,
        questions_per_avatar=payload.questions_per_avatar,
        current_avatar_index=0,
        current_question_index=0,
        total_questions=total_q,
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    logger.info(f"📋 Structured interview created — session={session_id}, total_q={total_q}")

    avatar_order = [
        {
            "index": i,
            "id": av.value,
            "name": _AVATAR_META[av]["name"],
            "emoji": _AVATAR_META[av]["emoji"],
            "title": _AVATAR_META[av]["title"],
        }
        for i, av in enumerate(STRUCTURED_AVATAR_ORDER)
    ]

    return StructuredStartResponse(
        session_id=session_id,
        candidate_name=payload.candidate_name,
        subject=payload.subject,
        questions_per_avatar=payload.questions_per_avatar,
        total_questions=total_q,
        avatar_order=avatar_order,
        message=(
            f"Structured interview started with {total_q} questions "
            f"({payload.questions_per_avatar} per avatar). "
            "Call /structured/getQuestion to receive the first question."
        ),
    )


# ── GET /structured/getQuestion ────────────────────────────────────────────

@router.get(
    "/structured/getQuestion",
    summary="Get the next interview question from the current avatar",
    response_model=GetQuestionResponse,
)
async def structured_get_question(
    session_id: str = Query(..., description="Structured session ID."),
    db: Session = Depends(get_session),
):
    """
    Returns the next question for the candidate.
    The avatar is determined by the current position in the rotation.
    """
    stmt = select(InterviewSession).where(InterviewSession.session_id == session_id)
    db_session = db.exec(stmt).first()
    if not db_session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    if db_session.mode != InterviewMode.structured.value:
        raise HTTPException(status_code=400, detail="This endpoint is only for structured interviews.")
    if db_session.status != SessionStatus.active.value:
        raise HTTPException(status_code=400, detail="This interview session is no longer active.")
    if db_session.current_question_index >= db_session.total_questions:
        raise HTTPException(
            status_code=400,
            detail="All questions have been asked. Call /structured/finishInterview.",
        )

    # Determine current avatar
    q_idx = db_session.current_question_index
    qpa = db_session.questions_per_avatar
    avatar_idx = q_idx // qpa
    question_number_for_avatar = (q_idx % qpa) + 1

    avatar_type = STRUCTURED_AVATAR_ORDER[avatar_idx]
    meta = _AVATAR_META[avatar_type]

    # Fetch already-asked questions by this avatar to avoid repeats
    prev_stmt = (
        select(InterviewQuestionScore)
        .where(
            InterviewQuestionScore.session_id == session_id,
            InterviewQuestionScore.avatar == avatar_type.value,
        )
        .order_by(col(InterviewQuestionScore.question_index))
    )
    prev_scores = db.exec(prev_stmt).all()
    previous_questions = [s.question_text for s in prev_scores]

    # Generate question via AI
    prompt = _structured_question_prompt(
        avatar=avatar_type,
        question_number=question_number_for_avatar,
        total_for_avatar=qpa,
        subject=db_session.subject,
        previous_questions=previous_questions or None,
    )

    agent = Agent(
        name=f"{meta['name']} (Question Generator)",
        instructions=prompt,
        model=get_current_model(),
    )

    try:
        result = await Runner.run(agent, "Generate the interview question now.")
        question_text = result.final_output.strip().strip('"').strip("'")
        logger.info(
            f"❓ Question generated — session={session_id}, "
            f"q_idx={q_idx}, avatar={avatar_type.value}"
        )
    except Exception as e:
        handle_api_error(e)
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)[:200]}")

    # Log the question as an interviewer message
    _log_message(
        db, db_session,
        MessageRole.interviewer.value,
        question_text,
        avatar=avatar_type.value,
    )

    return GetQuestionResponse(
        session_id=session_id,
        question_index=q_idx,
        total_questions=db_session.total_questions,
        avatar_id=avatar_type.value,
        avatar_name=meta["name"],
        avatar_emoji=meta["emoji"],
        avatar_title=meta["title"],
        question_number_for_avatar=question_number_for_avatar,
        questions_per_avatar=qpa,
        question_text=question_text,
        is_last_question=(q_idx == db_session.total_questions - 1),
    )


# ── POST /structured/submitAnswer ─────────────────────────────────────────

@router.post(
    "/structured/submitAnswer",
    summary="Submit the candidate's answer and receive an AI score (0-100)",
    response_model=SubmitAnswerResponse,
)
async def structured_submit_answer(
    payload: SubmitAnswerRequest,
    db: Session = Depends(get_session),
):
    """
    Scores the candidate's answer via AI and advances the question pointer.
    Returns score, feedback, and whether the interview is complete.
    """
    stmt = select(InterviewSession).where(InterviewSession.session_id == payload.session_id)
    db_session = db.exec(stmt).first()
    if not db_session:
        raise HTTPException(status_code=404, detail=f"Session '{payload.session_id}' not found.")
    if db_session.mode != InterviewMode.structured.value:
        raise HTTPException(status_code=400, detail="This endpoint is only for structured interviews.")
    if db_session.status != SessionStatus.active.value:
        raise HTTPException(status_code=400, detail="This interview session is no longer active.")
    if db_session.current_question_index >= db_session.total_questions:
        raise HTTPException(
            status_code=400,
            detail="All questions already answered. Call /structured/finishInterview.",
        )

    q_idx = db_session.current_question_index
    qpa = db_session.questions_per_avatar
    avatar_idx = q_idx // qpa
    avatar_type = STRUCTURED_AVATAR_ORDER[avatar_idx]
    meta = _AVATAR_META[avatar_type]

    # Retrieve the last interviewer message (the question) for this session
    last_q_stmt = (
        select(InterviewMessage)
        .where(
            InterviewMessage.session_id == payload.session_id,
            InterviewMessage.role == MessageRole.interviewer.value,
            InterviewMessage.avatar == avatar_type.value,
        )
        .order_by(col(InterviewMessage.message_index).desc())
    )
    last_q_msg = db.exec(last_q_stmt).first()
    question_text = last_q_msg.content if last_q_msg else "(question not found)"

    # Log candidate's answer
    _log_message(db, db_session, MessageRole.candidate.value, payload.answer)

    # Score via AI
    scoring_prompt = _structured_scoring_prompt(
        avatar=avatar_type,
        question=question_text,
        answer=payload.answer,
        subject=db_session.subject,
    )

    agent = Agent(
        name=f"{meta['name']} (Scorer)",
        instructions=scoring_prompt,
        model=get_current_model(),
    )

    try:
        result = await Runner.run(agent, "Score this answer now.")
        raw_output = result.final_output.strip()
        logger.info(f"📝 Answer scored — session={payload.session_id}, q_idx={q_idx}")
    except Exception as e:
        handle_api_error(e)
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)[:200]}")

    # Parse JSON output from AI
    score = 50.0
    ai_feedback = "Score could not be parsed."
    try:
        # Strip markdown code fences if present
        clean = raw_output
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*", "", clean)
            clean = re.sub(r"\s*```\s*$", "", clean)
        parsed = json.loads(clean)
        score = float(parsed.get("score", 50))
        score = max(0.0, min(100.0, score))
        ai_feedback = str(parsed.get("feedback", "No feedback provided."))
    except (json.JSONDecodeError, ValueError, TypeError):
        # Fallback: try to extract score from raw text
        m = re.search(r'"?score"?\s*:\s*(\d{1,3})', raw_output)
        if m:
            score = float(m.group(1))
            score = max(0.0, min(100.0, score))
        m2 = re.search(r'"?feedback"?\s*:\s*"([^"]+)"', raw_output)
        if m2:
            ai_feedback = m2.group(1)
        logger.warning(f"⚠️ Could not parse scoring JSON, used fallback. Raw: {raw_output[:200]}")

    # Persist question score
    qs = InterviewQuestionScore(
        session_id=payload.session_id,
        question_index=q_idx,
        avatar=avatar_type.value,
        question_text=question_text,
        answer_text=payload.answer,
        score=score,
        ai_feedback=ai_feedback,
    )
    db.add(qs)

    # Log AI feedback as interviewer message
    feedback_msg = f"**Score: {score}/100** — {ai_feedback}"
    _log_message(db, db_session, MessageRole.interviewer.value, feedback_msg, avatar=avatar_type.value)

    # Advance question pointer
    db_session.current_question_index = q_idx + 1
    new_avatar_idx = (q_idx + 1) // qpa if (q_idx + 1) < db_session.total_questions else avatar_idx
    db_session.current_avatar_index = new_avatar_idx
    db.add(db_session)
    db.commit()

    is_complete = (q_idx + 1) >= db_session.total_questions

    # Determine next avatar info
    next_avatar_id = None
    next_avatar_name = None
    if not is_complete:
        next_av = STRUCTURED_AVATAR_ORDER[new_avatar_idx]
        next_avatar_id = next_av.value
        next_avatar_name = _AVATAR_META[next_av]["name"]

    progress = f"{q_idx + 1}/{db_session.total_questions}"

    return SubmitAnswerResponse(
        session_id=payload.session_id,
        question_index=q_idx,
        avatar_id=avatar_type.value,
        avatar_name=meta["name"],
        avatar_emoji=meta["emoji"],
        question_text=question_text,
        answer_text=payload.answer,
        score=score,
        ai_feedback=ai_feedback,
        is_interview_complete=is_complete,
        next_avatar_id=next_avatar_id,
        next_avatar_name=next_avatar_name,
        progress=progress,
    )


# ── POST /structured/finishInterview ───────────────────────────────────────

@router.post(
    "/structured/finishInterview",
    summary="Finish the structured interview and get a final scorecard + report",
    response_model=FinishInterviewResponse,
)
async def structured_finish_interview(
    session_id: str = Query(..., description="Structured session ID."),
    db: Session = Depends(get_session),
):
    """
    Calculates normalised scores per avatar and overall, generates a
    detailed final report via AI, and marks the session as completed.
    """
    stmt = select(InterviewSession).where(InterviewSession.session_id == session_id)
    db_session = db.exec(stmt).first()
    if not db_session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    if db_session.mode != InterviewMode.structured.value:
        raise HTTPException(status_code=400, detail="This endpoint is only for structured interviews.")

    # Fetch all question scores
    qs_stmt = (
        select(InterviewQuestionScore)
        .where(InterviewQuestionScore.session_id == session_id)
        .order_by(col(InterviewQuestionScore.question_index))
    )
    all_scores = db.exec(qs_stmt).all()

    if not all_scores:
        raise HTTPException(
            status_code=400,
            detail="No answers have been submitted yet. Nothing to finish.",
        )

    # Group scores by avatar
    scores_by_avatar: dict[str, list[dict]] = {}
    for s in all_scores:
        scores_by_avatar.setdefault(s.avatar, []).append({
            "question_index": s.question_index,
            "question": s.question_text,
            "answer": s.answer_text,
            "score": s.score,
            "feedback": s.ai_feedback,
        })

    # Calculate per-avatar averages
    avatar_scores_list = []
    all_raw_scores = []
    for avatar_key, scores in scores_by_avatar.items():
        meta = _AVATAR_META.get(AvatarType(avatar_key), {})
        avg = sum(s["score"] for s in scores) / len(scores) if scores else 0
        all_raw_scores.extend(s["score"] for s in scores)
        avatar_scores_list.append({
            "avatar_id": avatar_key,
            "avatar_name": meta.get("name", avatar_key),
            "avatar_emoji": meta.get("emoji", ""),
            "avatar_title": meta.get("title", ""),
            "questions_answered": len(scores),
            "average_score": round(avg, 1),
            "individual_scores": [
                {"q": s["question"][:100], "score": s["score"]} for s in scores
            ],
        })

    # Overall score (simple mean)
    overall = round(sum(all_raw_scores) / len(all_raw_scores), 1) if all_raw_scores else 0.0

    # Generate detailed AI report
    report_prompt = _structured_final_report_prompt(
        scores_by_avatar=scores_by_avatar,
        candidate_name=db_session.candidate_name,
        subject=db_session.subject,
    )

    agent = Agent(
        name="Interview Report Analyst",
        instructions=report_prompt,
        model=get_current_model(),
    )

    try:
        result = await Runner.run(agent, "Generate the final interview report now.")
        detailed_report = result.final_output
        logger.info(f"📊 Structured report generated — session={session_id}, score={overall}")
    except Exception as e:
        handle_api_error(e)
        # Produce a basic report if AI fails
        detailed_report = (
            f"## Overall Score: {overall}/100\n\n"
            "_(Detailed AI report generation failed. Scores above are calculated from individual answers.)_"
        )

    # Persist feedback and update session
    _log_feedback(db, session_id, detailed_report)

    db_session.overall_score = overall
    db_session.status = SessionStatus.completed.value
    db_session.ended_at = datetime.utcnow()
    db.add(db_session)
    db.commit()

    # Build question scores list for response
    question_scores_out = [
        {
            "question_index": s.question_index,
            "avatar": s.avatar,
            "avatar_name": _AVATAR_META.get(AvatarType(s.avatar), {}).get("name", s.avatar),
            "question": s.question_text,
            "answer": s.answer_text[:200],
            "score": s.score,
            "feedback": s.ai_feedback,
        }
        for s in all_scores
    ]

    return FinishInterviewResponse(
        session_id=session_id,
        candidate_name=db_session.candidate_name,
        subject=db_session.subject,
        total_questions_answered=len(all_scores),
        overall_score=overall,
        avatar_scores=avatar_scores_list,
        detailed_report=detailed_report,
        question_scores=question_scores_out,
    )
