from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from agents.tool import Tool
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage
from openai.types.responses.response_output_text import ResponseOutputText


class OfflineEchoModel(Model):
    """A minimal offline Model implementation for running local tests without external LLM calls.

    It returns a deterministic assistant message and does not attempt any tool calling.
    """

    def __init__(self, prefix: str = "OFFLINE"):
        self.prefix = prefix

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any | None,
    ) -> ModelResponse:
        if isinstance(input, str):
            user_text = input
        else:
            # Best-effort extraction of last user message
            user_text = ""
            for item in reversed(input):
                if isinstance(item, dict) and item.get("role") == "user":
                    content = item.get("content")
                    if isinstance(content, str):
                        user_text = content
                    break

        text = f"{self.prefix}: simulated response for: {user_text[:200]}"

        message = ResponseOutputMessage(
            id=f"offline_{uuid.uuid4().hex}",
            type="message",
            role="assistant",
            status="completed",
            content=[
                ResponseOutputText(
                    type="output_text",
                    text=text,
                    annotations=[],
                )
            ],
        )

        return ModelResponse(output=[message], usage=Usage(requests=1), response_id="offline")

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        # Streaming isn't needed for the local test suite.
        # Provide an empty stream to satisfy the interface.
        if False:  # pragma: no cover
            yield cast(TResponseStreamEvent, {})
        return
