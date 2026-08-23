"""Structured routing between chat, tools, Text-to-SQL, and clarification."""

import re

from app.core.config import settings
from app.llm.qwen_client import generate_structured
from app.orchestration.models import RouteDecision
from app.prompts import load_prompt, render_prompt
from app.tools.registry import list_tool_definitions


def is_simple_chat_message(question: str) -> bool:
    """Recognize common no-data messages without an unnecessary model call."""
    normalized = re.sub(r"\s+", " ", question.strip().lower())
    normalized = normalized.rstrip(".!? ")
    return normalized in {
        "hello", "hi", "hey", "hello there", "hi there", "hey there",
        "good morning", "good afternoon", "good evening", "how are you",
        "thanks", "thank you", "thx", "thank you very much",
        "what can you do", "how can you help me", "how can you help",
    }


async def route_question(question: str) -> RouteDecision:
    """Route one question using metadata only; no tool implementation is shown to the model."""
    if is_simple_chat_message(question):
        return RouteDecision(action="chat", reason="Message does not require Sales data access.")

    tools = [definition.model_dump() for definition in list_tool_definitions()]
    decision = await generate_structured(
        system_prompt=load_prompt("router_system_v1.txt"),
        user_prompt=render_prompt("router_user_v1.txt", question=question, tools=tools),
        response_model=RouteDecision,
        temperature=0,
        max_output_tokens=200,
        operation_name="router.decide",
        timeout_seconds=settings.ROUTER_TIMEOUT_SECONDS,
        result_attributes=lambda result: {
            "app.route": result.action,
            "router.reason": result.reason,
            "app.tool_name": result.tool_name,
            "router.arguments": str(result.arguments),
            "router.clarification_requested": result.action == "clarify",
        },
    )
    if decision.action == "tool" and not decision.tool_name:
        return RouteDecision(
            action="clarify",
            clarification_question=load_prompt("clarification_missing_tool_v1.txt"),
            reason="Tool route omitted a tool name.",
        )
    return decision
