"""Centralized OpenTelemetry tracing configured for Phoenix OTLP/HTTP."""

import json
import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

from app.core.config import settings


logger = logging.getLogger(__name__)
_TRACER_NAME = "enterprise_conversational_agent"
_initialized = False
_provider: Optional[TracerProvider] = None
OPENINFERENCE_SPAN_KIND = "openinference.span.kind"
INPUT_VALUE = "input.value"
INPUT_MIME_TYPE = "input.mime_type"
OUTPUT_VALUE = "output.value"
OUTPUT_MIME_TYPE = "output.mime_type"


def setup_tracing() -> None:
    """Initialize the global provider once; exporter setup failures never stop the app."""
    global _initialized, _provider
    if _initialized:
        return
    _initialized = True
    try:
        resource = Resource.create({
            SERVICE_NAME: settings.APP_NAME,
            "openinference.project.name": settings.PHOENIX_PROJECT_NAME,
        })
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=settings.PHOENIX_ENDPOINT,
            headers={"x-project-name": settings.PHOENIX_PROJECT_NAME},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _provider = provider
    except Exception:
        logger.exception("Phoenix tracing initialization failed; application tracing will remain non-fatal.")


def get_tracer() -> trace.Tracer:
    """Return the one application tracer."""
    return trace.get_tracer(_TRACER_NAME)


def shutdown_tracing() -> None:
    """Flush queued spans during graceful FastAPI shutdown without affecting shutdown."""
    if _provider is None:
        return
    try:
        _provider.force_flush()
        _provider.shutdown()
    except Exception:
        logger.exception("Phoenix tracing shutdown failed.")


@contextmanager
def traced_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    span_kind: str = "CHAIN",
    input_value: Optional[str] = None,
    input_mime_type: str = "text/plain",
) -> Iterator[Span]:
    """Create an active OpenInference child span and consistently record its outcome."""
    with get_tracer().start_as_current_span(name) as span:
        set_span_attributes(span, {
            OPENINFERENCE_SPAN_KIND: span_kind,
            INPUT_VALUE: input_value,
            INPUT_MIME_TYPE: input_mime_type if input_value is not None else None,
            **(attributes or {}),
        })
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        else:
            if getattr(span, "status", Status(StatusCode.UNSET)).status_code == StatusCode.UNSET:
                span.set_status(Status(StatusCode.OK))


def set_span_attributes(span: Span, attributes: Dict[str, Any]) -> None:
    """Set only non-null scalar/list attributes accepted by OpenTelemetry."""
    for key, value in attributes.items():
        if value is not None:
            span.set_attribute(key, value)


def mark_span_error(span: Span, exc: Exception) -> None:
    """Record a caught exception when business logic handles it instead of re-raising."""
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


def mark_span_error_message(span: Span, message: str) -> None:
    """Mark an expected business or validation failure as an error without raising."""
    span.set_status(Status(StatusCode.ERROR, message))


def set_span_output(span: Span, value: Any, mime_type: str = "text/plain") -> None:
    """Set Phoenix-recognized bounded output attributes."""
    if value is not None:
        span.set_attribute(OUTPUT_VALUE, value if isinstance(value, str) else compact_json(value))
        span.set_attribute(OUTPUT_MIME_TYPE, mime_type)


def trace_id(span: Optional[Span] = None) -> str:
    """Return the current trace ID as a Phoenix-searchable 32-character hex string."""
    context = (span or trace.get_current_span()).get_span_context()
    return format(context.trace_id, "032x") if context.trace_id else ""


def compact_json(value: Any, max_chars: int = 4000) -> str:
    """Serialize bounded diagnostic context without building a redaction framework."""
    serialized = json.dumps(value, default=str, ensure_ascii=False)
    return serialized if len(serialized) <= max_chars else serialized[:max_chars] + "...<truncated>"


def result_summary(data: Any) -> Dict[str, Any]:
    """Return bounded result metadata suitable for traces, never full query payloads."""
    preview_rows = settings.TRACE_RESULT_PREVIEW_ROWS
    if isinstance(data, list):
        return {"row_count": len(data), "result_preview": compact_json(data[:preview_rows])}
    if isinstance(data, dict):
        preview = {
            key: value[:preview_rows] if isinstance(value, list) else value
            for key, value in data.items()
        }
        return {"row_count": len(data), "result_preview": compact_json(preview)}
    return {"row_count": 0, "result_preview": compact_json(data)}
