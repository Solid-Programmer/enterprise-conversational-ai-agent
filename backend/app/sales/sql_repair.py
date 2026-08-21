"""Bounded structured SQL repair for failed generated queries."""

from app.llm.qwen_client import generate_structured
from app.orchestration.models import SQLGeneration


REPAIR_SYSTEM_PROMPT = """You repair one Microsoft SQL Server T-SQL SELECT query.
Return only the supplied JSON schema containing corrected sql or null.
Use only the supplied schema context and business rules. Output exactly one SELECT or CTE leading to SELECT.
Never output prose, DDL, DML, EXEC, stored procedures, comments, or multiple statements."""


def repair_sql(question: str, generated_sql: str, error: str, context: str, attempt_number: int) -> SQLGeneration:
    """Request one deterministic-temperature repair; the orchestrator enforces the attempt bound."""
    return generate_structured(
        system_prompt=REPAIR_SYSTEM_PROMPT,
        user_prompt=(
            f"Original user question:\n{question}\n\nGenerated SQL:\n{generated_sql}"
            f"\n\nValidation or execution error:\n{error}\n\nRelevant schema context and business rules:\n{context}"
        ),
        response_model=SQLGeneration,
        temperature=0,
        operation_name="sql.repair",
        trace_attributes={
            "repair.attempt": attempt_number,
            "repair.original_sql": generated_sql,
            "failure.reason": error,
        },
        result_attributes=lambda result: {"repair.repaired_sql": result.sql},
    )
