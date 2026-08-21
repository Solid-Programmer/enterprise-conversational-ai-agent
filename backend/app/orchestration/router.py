"""Structured Qwen/Ollama routing between tools, Text-to-SQL, and clarification."""

from app.llm.qwen_client import generate_structured
from app.orchestration.models import RouteDecision
from app.tools.registry import list_tool_definitions


ROUTER_SYSTEM_PROMPT = """You route Sales analytics requests. Return only the supplied JSON schema.
Choose action=tool only when one listed deterministic business tool clearly covers the request.
Choose action=text_to_sql for flexible or ad-hoc read-only analytics not covered by one tool.
Choose action=clarify when business meaning or required filters are materially ambiguous.
An explicit entity lookup or filter is not ambiguous merely because no deterministic tool matches it.
For example, a request for credit-card details for a specified sales order must use text_to_sql,
not clarify: the order number is an explicit filter and the request can be answered from schema context.
Never ask the user which tool should be used. Tool selection is the router's responsibility.
Never choose HITL. For tool, use an exact listed tool_name and only supported arguments.
For clarify, provide a short clarification_question. Do not generate SQL."""


def route_question(question: str) -> RouteDecision:
    """Route one question using metadata only; no tool implementation is shown to the model."""
    tools = [definition.model_dump() for definition in list_tool_definitions()]
    decision = generate_structured(
        system_prompt=ROUTER_SYSTEM_PROMPT,
        user_prompt=f"User question:\n{question}\n\nAvailable deterministic tools:\n{tools}",
        response_model=RouteDecision,
        temperature=0,
        operation_name="router.decide",
        result_attributes=lambda result: {
            "app.route": result.action,
            "router.reason": result.reason,
            "app.tool_name": result.tool_name,
            "router.arguments": str(result.arguments),
            "router.clarification_requested": result.action == "clarify",
        },
    )
    if decision.action == "tool" and not decision.tool_name:
        return RouteDecision(action="clarify", clarification_question="Which sales analysis would you like me to run?", reason="Tool route omitted a tool name.")
    return decision
