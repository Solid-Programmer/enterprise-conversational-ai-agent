"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import asyncio
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.api.chat import router as chat_router
from app.core.config import settings
from app.core.execution import StageTimeoutError, run_with_timeout
from app.observability.tracing import (
    INPUT_MIME_TYPE,
    OPENINFERENCE_SPAN_KIND,
    set_span_attributes,
    set_span_output,
    setup_tracing,
    shutdown_tracing,
    trace_id,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_tracing()
    try:
        yield
    finally:
        shutdown_tracing()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.include_router(chat_router)
_tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)


@app.middleware("http")
async def trace_chat_request(request: Request, call_next):
    """Create the one root trace and overall timeout before endpoint dependencies run."""
    if request.url.path != "/api/chat":
        return await call_next(request)

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    with _tracer.start_as_current_span("chat.request") as root_span:
        set_span_attributes(root_span, {
            OPENINFERENCE_SPAN_KIND: "AGENT",
            INPUT_MIME_TYPE: "text/plain",
            "app.request_id": request_id,
            "request.id": request_id,
        })
        try:
            response = await run_with_timeout(
                call_next(request),
                timeout_seconds=settings.REQUEST_TIMEOUT_SECONDS,
                stage="chat.request",
            )
            final_status = "success" if response.status_code < 400 else "error"
            set_span_attributes(root_span, {"app.final_status": final_status, "http.status_code": response.status_code})
            if response.status_code >= 400:
                root_span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
            else:
                root_span.set_status(Status(StatusCode.OK))
            return response
        except StageTimeoutError:
            logger.error("Chat request timed out before completion: request_id=%s", request_id)
            result = {
                "status": "error",
                "route": None,
                "tool_name": None,
                "sql": None,
                "answer": "The request took too long to complete. Please try again.",
                "data": None,
                "message": None,
                "metadata": {"trace_id": trace_id(root_span), "request_id": request_id, "timeout_stage": "chat.request"},
            }
            set_span_attributes(root_span, {"app.final_status": "error", "timeout": True, "error.type": "timeout"})
            set_span_output(root_span, result, mime_type="application/json")
            root_span.set_status(Status(StatusCode.ERROR, "timeout"))
            return JSONResponse(status_code=504, content=result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Unhandled chat request failure: request_id=%s", request_id)
            root_span.record_exception(exc)
            root_span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
