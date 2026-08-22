"""Bounded structured SQL repair for failed generated queries."""

from app.llm.qwen_client import generate_structured
from app.core.config import settings
from app.orchestration.models import SQLGeneration
from app.prompts import load_prompt, render_prompt


async def repair_sql(question: str, generated_sql: str, error: str, context: str, attempt_number: int) -> SQLGeneration:
    """Request one deterministic-temperature repair; the orchestrator enforces the attempt bound."""
    return await generate_structured(
        system_prompt=load_prompt("sql_repair_system_v1.txt"),
        user_prompt=render_prompt(
            "sql_repair_user_v1.txt",
            question=question,
            generated_sql=generated_sql,
            error=error,
            context=context,
        ),
        response_model=SQLGeneration,
        temperature=0,
        max_output_tokens=500,
        operation_name="sql.repair",
        timeout_seconds=settings.SQL_REPAIR_TIMEOUT_SECONDS,
        trace_attributes={
            "repair.attempt": attempt_number,
            "repair.original_sql": generated_sql,
            "failure.reason": error,
        },
        result_attributes=lambda result: {"repair.repaired_sql": result.sql},
    )
