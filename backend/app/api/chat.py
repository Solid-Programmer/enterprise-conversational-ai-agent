"""Main chat endpoint for the synchronous Sales orchestration flow."""

import time
import uuid
import asyncio
import logging
from contextlib import nullcontext

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field

from app.auth.rbac import AuthorizationContext, get_authorization_context
from app.core.execution import StageTimeoutError
from app.observability.tracing import (
    INPUT_MIME_TYPE,
    INPUT_VALUE,
    OPENINFERENCE_SPAN_KIND,
    mark_span_error_message,
    result_summary,
    set_span_attributes,
    set_span_output,
    trace_id,
    traced_span,
)
from app.llm.answer_generator import generate_answer
from app.orchestration.models import ChatResult
from app.orchestration.orchestrator import SalesOrchestrator


router = APIRouter(prefix="/api", tags=["chat"])
_orchestrator = SalesOrchestrator()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


@router.post("/chat", response_model=ChatResult)
async def chat(
    request: ChatRequest,
    http_request: Request,
    authorization: AuthorizationContext = Depends(get_authorization_context),
) -> ChatResult:
    """Route and process one independent Sales question."""
    request_id = getattr(http_request.state, "request_id", str(uuid.uuid4()))
    started = time.perf_counter()

    # The middleware owns the one chat.request root span, including dependencies.
    with nullcontext(trace.get_current_span()) as root_span:
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
        async def process_request() -> ChatResult:
            result = await _orchestrator.handle(request.message, authorization)
            if result.status == "success" and not result.answer:
                try:
                    result.answer = (await generate_answer(request.message, result.data, result.sql)).answer
                except StageTimeoutError:
                    raise
                except Exception:
                    result.answer = "The query completed successfully. Review the structured data for details."
            return result

        try:
            result = await process_request()
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
            result.metadata.update({"trace_id": trace_id(root_span), "request_id": request_id})
            return result
        except StageTimeoutError as exc:
            logger.error("Chat request timed out: request_id=%s stage=%s", request_id, exc.stage)
            result = ChatResult(
                status="error",
                answer="The request took too long to complete. Please try again.",
                data=None,
                metadata={"trace_id": trace_id(root_span), "request_id": request_id, "timeout_stage": exc.stage},
            )
            set_span_attributes(root_span, {"app.final_status": "error", "timeout": True, "error.type": "timeout"})
            set_span_output(root_span, {"status": result.status, "answer": result.answer}, mime_type="application/json")
            return JSONResponse(status_code=504, content=result.model_dump())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            root_span.record_exception(exc)
            root_span.set_status(Status(StatusCode.ERROR, str(exc)))
            logger.exception("Unexpected chat failure: request_id=%s", request_id)
            result = ChatResult(
                status="error",
                answer="The request could not be completed. Please try again.",
                data=None,
                metadata={"trace_id": trace_id(root_span), "request_id": request_id},
            )
            return JSONResponse(status_code=500, content=result.model_dump())
