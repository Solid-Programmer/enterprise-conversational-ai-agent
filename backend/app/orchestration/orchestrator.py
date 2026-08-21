"""Bounded synchronous control flow for the Sales runtime."""
from app.db.sql_executor import SQLExecutionError, execute_validated_sql
from app.db.sql_validator import validate_sql
from app.orchestration.clarification import clarification_result
from app.orchestration.hitl import human_review_result
from app.orchestration.models import ChatResult
from app.orchestration.router import route_question
from app.retrieval.context_builder import build_text_to_sql_context
from app.sales.sql_repair import repair_sql
from app.sales.text_to_sql import TextToSQLGenerator
from app.tools.registry import execute_tool, get_registered_tool
from app.observability.tracing import mark_span_error, result_summary, set_span_attributes, set_span_output, traced_span


MAX_REPAIR_ATTEMPTS = 2


class SalesOrchestrator:
    """Route first, then run exactly one deterministic tool or Text-to-SQL path."""

    def handle(self, question: str) -> ChatResult:
        if not question or not question.strip():
            return ChatResult(status="error", message="A non-empty message is required.")
        try:
            decision = route_question(question)
        except Exception as exc:
            return human_review_result(question, "Routing could not safely complete.", error=str(exc))

        if decision.action == "clarify":
            return clarification_result(question, decision)
        if decision.action == "tool":
            return self._run_tool(question, decision.tool_name or "", decision.arguments)
        return self._run_text_to_sql(question)

    def _run_tool(self, question: str, tool_name: str, arguments: dict) -> ChatResult:
        if get_registered_tool(tool_name) is None:
            return human_review_result(question, "Router selected an unregistered tool.", error=tool_name, route="tool")
        with traced_span("tool.execute", {
            "app.tool_name": tool_name,
            "tool.name": tool_name,
            "tool.parameters": str(arguments),
        }, span_kind="TOOL", input_value=str(arguments), input_mime_type="application/json") as span:
            try:
                data = execute_tool(tool_name, arguments)
                set_span_attributes(span, {"tool.execution_success": True, **result_summary(data)})
                set_span_output(span, result_summary(data), mime_type="application/json")
                return ChatResult(status="success", route="tool", tool_name=tool_name, data=data, metadata={"tool_arguments": arguments})
            except Exception as exc:
                mark_span_error(span, exc)
                set_span_attributes(span, {"tool.execution_success": False, "failure.stage": "tool.execute", "failure.reason": str(exc)})
                return human_review_result(question, "Deterministic tool execution failed without a safe fallback.", error=str(exc), route="tool")

    def _run_text_to_sql(self, question: str) -> ChatResult:
        try:
            context = build_text_to_sql_context(question)
            generated = TextToSQLGenerator().generate_sql(question, context)
        except Exception as exc:
            return human_review_result(question, "Text-to-SQL context retrieval or generation failed.", error=str(exc), route="text_to_sql")
        if not generated.sql:
            return human_review_result(question, "The model could not safely produce SQL.", route="text_to_sql")

        candidate_sql = generated.sql
        last_error = ""
        for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
            validation = validate_sql(candidate_sql)
            if validation.valid:
                try:
                    data = execute_validated_sql(validation)
                    return ChatResult(
                        status="success",
                        route="text_to_sql",
                        sql=validation.normalized_sql,
                        data=data,
                        metadata={"repair_attempts": attempt},
                    )
                except SQLExecutionError as exc:
                    last_error = exc.message
            else:
                last_error = "; ".join(validation.errors)

            if attempt == MAX_REPAIR_ATTEMPTS:
                break
            try:
                repaired = repair_sql(question, candidate_sql, last_error, context, attempt_number=attempt + 1)
            except Exception as exc:
                return human_review_result(
                    question,
                    "SQL repair could not safely complete.",
                    last_sql=candidate_sql,
                    error=str(exc),
                    route="text_to_sql",
                    repair_attempts=attempt,
                )
            if not repaired.sql:
                break
            candidate_sql = repaired.sql

        return human_review_result(
            question,
            "Generated SQL remained invalid or failed after the maximum two repair attempts.",
            last_sql=candidate_sql,
            error=last_error,
            route="text_to_sql",
            repair_attempts=MAX_REPAIR_ATTEMPTS,
        )
