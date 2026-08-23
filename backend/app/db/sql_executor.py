"""Read-only database execution, separate from deterministic SQL validation."""

import datetime
import asyncio
from decimal import Decimal
from typing import Any, Dict, List

from app.db.connection import get_db_connection
from app.db.sql_validator import SQLValidationResult
from app.core.config import settings
from app.core.execution import run_with_timeout
from app.observability.tracing import result_summary, set_span_attributes, set_span_output, traced_span
from app.security.pii_masking import mask_sensitive_result


class SQLExecutionError(RuntimeError):
    """Structured database error raised after a statement was validated."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def to_dict(self) -> Dict[str, str]:
        """Expose the database failure in an API-safe structured form."""
        return {"type": "sql_execution_error", "message": self.message}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return round(float(value), 4)
    if isinstance(value, float):
        return round(value, 4)
    return value


def _invalidate_failed_connection(connection: Any) -> None:
    """Discard a pooled connection after a database error or query timeout."""
    invalidate = getattr(connection, "invalidate", None)
    if callable(invalidate):
        invalidate()


def execute_validated_sql(validation: SQLValidationResult, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute only a previously valid SQLGlot result and return JSON-serializable rows."""
    if not validation.valid or not validation.normalized_sql:
        raise ValueError("Only successfully validated SQL can be executed.")
    with traced_span("sql.execute", {}, span_kind="TOOL", input_value=validation.normalized_sql) as span:
        conn = None
        try:
            conn = get_db_connection()
            driver_connection = getattr(conn, "driver_connection", conn)
            driver_connection.timeout = int(settings.SQL_EXECUTION_TIMEOUT_SECONDS)
            cursor = conn.cursor()
            cursor.execute(validation.normalized_sql, params)
            if not cursor.description:
                results: List[Dict[str, Any]] = []
            else:
                columns = [column[0] for column in cursor.description]
                results = [{name: _normalize_value(value) for name, value in zip(columns, row)} for row in cursor.fetchall()]
            results = mask_sensitive_result(results)
            set_span_attributes(span, {"sql.execution_success": True, **result_summary(results)})
            set_span_output(span, result_summary(results), mime_type="application/json")
            return results
        except Exception as exc:
            if conn is not None:
                try:
                    _invalidate_failed_connection(conn)
                except Exception:
                    # The original database failure is the useful error to return.
                    pass
            set_span_attributes(span, {"sql.execution_success": False, "failure.stage": "sql.execute", "failure.reason": str(exc)})
            raise SQLExecutionError(str(exc)) from exc
        finally:
            if conn is not None:
                conn.close()


async def execute_validated_sql_with_timeout(
    validation: SQLValidationResult,
    params: tuple = (),
) -> List[Dict[str, Any]]:
    """Run the existing blocking SQL executor in a bounded worker thread."""
    return await run_with_timeout(
        asyncio.to_thread(execute_validated_sql, validation, params),
        timeout_seconds=settings.SQL_EXECUTION_TIMEOUT_SECONDS,
        stage="sql.execute",
    )


def execute_sql_query(sql_query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a trusted, static query embedded in deterministic Python business tools.

    Generated user SQL must instead use validate_sql followed by execute_validated_sql.
    """
    if not sql_query or not sql_query.lstrip().upper().startswith(("SELECT", "WITH")):
        raise ValueError("Trusted deterministic tool query must be a SELECT or CTE.")
    return execute_validated_sql(SQLValidationResult(valid=True, normalized_sql=sql_query), params)
