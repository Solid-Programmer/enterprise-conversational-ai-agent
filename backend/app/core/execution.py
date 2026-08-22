"""Centralized timeout, cancellation, and stage logging for request work."""

import asyncio
import logging
import time
from typing import Awaitable, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


logger = logging.getLogger(__name__)
T = TypeVar("T")


class StageTimeoutError(TimeoutError):
    """Raised when a bounded application stage exceeds its configured limit."""

    def __init__(self, stage: str, timeout_seconds: float) -> None:
        self.stage = stage
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Stage '{stage}' timed out after {timeout_seconds:g} seconds.")


def _record_stage_outcome(*, stage: str, duration_ms: float, error_type: str | None = None) -> None:
    span = trace.get_current_span()
    span.set_attribute("stage.name", stage)
    span.set_attribute("stage.duration_ms", duration_ms)
    if error_type:
        span.set_attribute("error.type", error_type)
        span.set_status(Status(StatusCode.ERROR, error_type))


async def run_with_timeout(
    awaitable: Awaitable[T],
    *,
    timeout_seconds: float,
    stage: str,
) -> T:
    """Await one stage with consistent timeout logging and trace error semantics."""
    started = time.perf_counter()
    logger.info("START stage=%s", stage)
    try:
        result = await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except asyncio.CancelledError:
        logger.info("CANCELLED stage=%s", stage)
        raise
    except asyncio.TimeoutError as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        _record_stage_outcome(stage=stage, duration_ms=duration_ms, error_type="timeout")
        logger.error("ERROR stage=%s type=timeout duration_ms=%s", stage, duration_ms)
        raise StageTimeoutError(stage, timeout_seconds) from exc
    except StageTimeoutError:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        _record_stage_outcome(stage=stage, duration_ms=duration_ms, error_type="timeout")
        logger.error("ERROR stage=%s type=timeout duration_ms=%s", stage, duration_ms)
        raise
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        span = trace.get_current_span()
        span.record_exception(exc)
        _record_stage_outcome(stage=stage, duration_ms=duration_ms, error_type=type(exc).__name__)
        logger.exception("ERROR stage=%s type=%s duration_ms=%s", stage, type(exc).__name__, duration_ms)
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    _record_stage_outcome(stage=stage, duration_ms=duration_ms)
    logger.info("END stage=%s duration_ms=%s", stage, duration_ms)
    return result
