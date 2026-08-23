"""Bounded asynchronous control flow for the Sales runtime."""
import asyncio

from app.core.config import settings
from app.core.execution import StageTimeoutError, run_with_timeout
from app.db.sql_executor import SQLExecutionError, execute_validated_sql_with_timeout
from app.auth.rbac import AuthorizationContext
from app.db.sql_validator import authorize_sql_tables, validate_sql
from app.orchestration.clarification import clarification_result
from app.orchestration.hitl import human_review_result
from app.orchestration.models import ChatResult
from app.orchestration.router import route_question
from app.retrieval.context_builder import build_text_to_sql_context
from app.sales.sql_repair import repair_sql
from app.sales.text_to_sql import TextToSQLGenerator
from app.tools.registry import execute_tool, get_registered_tool
from app.observability.tracing import mark_span_error, result_summary, set_span_attributes, set_span_output, traced_span


MAX_REPAIR_ATTEMPTS = 1


class SalesOrchestrator:
    """Route first, then run exactly one chat, tool, or Text-to-SQL path."""

    async def handle(self, question: str, authorization: AuthorizationContext) -> ChatResult:
        if not question or not question.strip():
            return ChatResult(status="error", message="A non-empty message is required.")
        try:
            decision = await route_question(question)
        except StageTimeoutError:
            raise
        except Exception as exc:
            return human_review_result(question, "Routing could not safely complete.", error=str(exc))

        if decision.action == "clarify":
            return clarification_result(question, decision)
        if decision.action == "chat":
            return self._run_chat(question)
        if decision.action == "tool":
            return await self._run_tool(question, decision.tool_name or "", decision.arguments, authorization)
        return await self._run_text_to_sql(question, authorization)

    def _run_chat(self, question: str) -> ChatResult:
        """Return a concise no-data response without invoking retrieval or analytical paths."""
        normalized = question.strip().lower()
        if any(phrase in normalized for phrase in ("thank", "thx")):
            answer = "You're welcome."
        elif "what can you do" in normalized or "how can you help" in normalized:
            answer = (
                "I can help analyze sales, customers, territories, products, promotions, trends, "
                "and other questions available in the connected Sales data."
            )
        else:
            answer = "Hello! How can I help with your sales analysis today?"
        return ChatResult(status="success", route="chat", answer=answer, data=None)

    async def _run_tool(
        self,
        question: str,
        tool_name: str,
        arguments: dict,
        authorization: AuthorizationContext,
    ) -> ChatResult:
        tool = get_registered_tool(tool_name)
        if tool is None:
            return human_review_result(question, "Router selected an unregistered tool.", error=tool_name, route="tool")
        unauthorized_tables = sorted(tool.required_tables.difference(authorization.allowed_tables))
        if unauthorized_tables:
            return ChatResult(
                status="error",
                route="tool",
                tool_name=tool_name,
                answer="You do not have access to the data required for this request.",
                message="Tool table access was denied.",
                metadata={
                    "authorization_allowed": False,
                    "unauthorized_tables": unauthorized_tables,
                },
            )
        with traced_span("tool.execute", {
            "app.tool_name": tool_name,
            "tool.name": tool_name,
            "tool.parameters": str(arguments),
            "authorization.tables_required": sorted(tool.required_tables),
            "authorization.role": authorization.role,
        }, span_kind="TOOL", input_value=str(arguments), input_mime_type="application/json") as span:
            try:
                data = await run_with_timeout(
                    asyncio.to_thread(execute_tool, tool_name, arguments),
                    timeout_seconds=settings.TOOL_TIMEOUT_SECONDS,
                    stage="tool.execute",
                )
                set_span_attributes(span, {"tool.execution_success": True, **result_summary(data)})
                set_span_output(span, result_summary(data), mime_type="application/json")
                return ChatResult(status="success", route="tool", tool_name=tool_name, data=data, metadata={"tool_arguments": arguments})
            except StageTimeoutError:
                raise
            except Exception as exc:
                mark_span_error(span, exc)
                set_span_attributes(span, {"tool.execution_success": False, "failure.stage": "tool.execute", "failure.reason": str(exc)})
                return human_review_result(question, "Deterministic tool execution failed without a safe fallback.", error=str(exc), route="tool")

    async def _run_text_to_sql(self, question: str, authorization: AuthorizationContext) -> ChatResult:
        try:
            context = await build_text_to_sql_context(question)
            generated = await TextToSQLGenerator().generate_sql(question, context)
        except StageTimeoutError:
            raise
        except Exception as exc:
            return human_review_result(question, "Text-to-SQL context retrieval or generation failed.", error=str(exc), route="text_to_sql")
        if not generated.sql:
            return human_review_result(question, "The model could not safely produce SQL.", route="text_to_sql")

        candidate_sql = generated.sql
        last_error = ""
        for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
            validation = validate_sql(candidate_sql)
            if validation.valid:
                table_authorization = authorize_sql_tables(
                    validation.normalized_sql or candidate_sql,
                    authorization.allowed_tables,
                    role=authorization.role,
                )
                if not table_authorization.authorized:
                    return ChatResult(
                        status="error",
                        route="text_to_sql",
                        answer="You do not have access to the data required for this request.",
                        message="SQL table access was denied.",
                        metadata={
                            "authorization_allowed": False,
                            "unauthorized_tables": table_authorization.unauthorized_tables,
                            "authorization_errors": table_authorization.errors,
                        },
                    )
                try:
                    data = await execute_validated_sql_with_timeout(validation)
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
                repaired = await repair_sql(question, candidate_sql, last_error, context, attempt_number=attempt + 1)
            except StageTimeoutError:
                raise
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
            "Generated SQL remained invalid or failed after one repair attempt.",
            last_sql=candidate_sql,
            error=last_error,
            route="text_to_sql",
            repair_attempts=MAX_REPAIR_ATTEMPTS,
        )
