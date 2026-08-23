"""Structured clarification responses for materially ambiguous business requests."""

from app.orchestration.models import ChatResult, RouteDecision
from app.observability.tracing import set_span_attributes, set_span_output, traced_span
from app.prompts import load_prompt


def clarification_result(question: str, decision: RouteDecision) -> ChatResult:
    """Return a safe clarification state without attempting SQL generation."""
    with traced_span("clarification.generate", {
        "failure.reason": decision.reason,
    }, span_kind="CHAIN", input_value=question) as span:
        prompt = decision.clarification_question or load_prompt("clarification_default_v1.txt")
        set_span_attributes(span, {"clarification.question": prompt})
        set_span_output(span, prompt)
        return ChatResult(status="clarification_required", message=prompt, metadata={"original_question": question, "reason": decision.reason})
