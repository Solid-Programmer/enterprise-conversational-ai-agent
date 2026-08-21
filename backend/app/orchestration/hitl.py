"""Structured escalation state; no human-review workflow is implied or invoked."""

from typing import Optional

from app.orchestration.models import ChatResult
from app.observability.tracing import mark_span_error_message, set_span_output, traced_span


def human_review_result(
    question: str,
    reason: str,
    last_sql: Optional[str] = None,
    error: Optional[str] = None,
    route: Optional[str] = None,
    repair_attempts: int = 0,
) -> ChatResult:
    """Return a bounded, explicit escalation result."""
    with traced_span("hitl.escalate", {
        "app.route": route,
        "failure.reason": reason,
        "failure.error": error,
        "repair.attempts": repair_attempts,
    }, span_kind="CHAIN", input_value=question) as span:
        result = ChatResult(
            status="requires_human_review",
            sql=last_sql,
            message="The request requires human review before it can be completed safely.",
            metadata={"original_question": question, "reason": reason, "last_sql": last_sql, "error": error},
        )
        set_span_output(span, {"reason": reason, "last_sql": last_sql, "error": error}, mime_type="application/json")
        mark_span_error_message(span, reason)
        return result
