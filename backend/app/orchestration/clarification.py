"""Structured clarification responses for materially ambiguous business requests."""

from app.orchestration.models import ChatResult, RouteDecision
from app.observability.tracing import set_span_attributes, set_span_output, traced_span


def clarification_result(question: str, decision: RouteDecision) -> ChatResult:
    """Return a safe clarification state without attempting SQL generation."""
    with traced_span("clarification.generate", {
        "failure.reason": decision.reason,
    }, span_kind="CHAIN", input_value=question) as span:
        prompt = decision.clarification_question or "Could you clarify the business metric, period, or entity you want to analyze?"
        set_span_attributes(span, {"clarification.question": prompt})
        set_span_output(span, prompt)
        return ChatResult(status="clarification_required", message=prompt, metadata={"original_question": question, "reason": decision.reason})
