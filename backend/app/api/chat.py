"""Main chat endpoint for the synchronous Sales orchestration flow."""

import time
import uuid

from fastapi import APIRouter, Depends
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field

from app.auth.rbac import AuthorizationContext, get_authorization_context
from app.observability.tracing import (
    INPUT_MIME_TYPE,
    INPUT_VALUE,
    OPENINFERENCE_SPAN_KIND,
    mark_span_error_message,
    result_summary,
    set_span_attributes,
    set_span_output,
    traced_span,
)
from app.llm.answer_generator import generate_answer
from app.orchestration.models import ChatResult
from app.orchestration.orchestrator import SalesOrchestrator


router = APIRouter(prefix="/api", tags=["chat"])
_orchestrator = SalesOrchestrator()
_tracer = trace.get_tracer(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


@router.post("/chat", response_model=ChatResult)
def chat(
    request: ChatRequest,
    authorization: AuthorizationContext = Depends(get_authorization_context),
) -> ChatResult:
    """Route and process one independent Sales question."""
    request_id = str(uuid.uuid4())
    started = time.perf_counter()

    with _tracer.start_as_current_span("chat.request") as root_span:
        set_span_attributes(root_span, {
            OPENINFERENCE_SPAN_KIND: "AGENT",
            INPUT_VALUE: request.message,
            INPUT_MIME_TYPE: "text/plain",
            "app.request_id": request_id,
            "request.id": request_id,
            "user.id": authorization.auth_subject,
            "app.user_id": authorization.user_id,
            "app.role": authorization.role,
            "app.allowed_table_count": len(authorization.allowed_tables),
        })
        try:
            result = _orchestrator.handle(request.message, authorization)
            if result.status == "success" and not result.answer:
                try:
                    result.answer = generate_answer(request.message, result.data, result.sql).answer
                except Exception:
                    result.answer = "The query completed successfully. Review the structured data for details."
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            with traced_span("response.finalize", {
                "app.route": result.route,
                "app.tool_name": result.tool_name,
                "app.final_status": result.status,
                "app.total_latency_ms": latency_ms,
                **result_summary(result.data),
            }, input_value=result.route or "no route") as response_span:
                set_span_output(response_span, {"status": result.status, "answer": result.answer, **result_summary(result.data)}, mime_type="application/json")
                if result.status in {"error", "requires_human_review"}:
                    mark_span_error_message(response_span, result.message or result.status)

            set_span_attributes(root_span, {
                "app.final_status": result.status,
                "app.route": result.route,
                "app.tool_name": result.tool_name,
                "app.total_latency_ms": latency_ms,
            })
            set_span_output(root_span, {"status": result.status, "route": result.route, "answer": result.answer}, mime_type="application/json")
            if result.status in {"error", "requires_human_review"}:
                mark_span_error_message(root_span, result.message or result.status)
            else:
                root_span.set_status(Status(StatusCode.OK))
            return result
        except Exception as exc:
            root_span.record_exception(exc)
            root_span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
