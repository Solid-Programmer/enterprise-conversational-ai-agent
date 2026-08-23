"""Authorization tests for deterministic tools' declared table requirements."""

import asyncio

from app.auth.rbac import AuthorizationContext
from app.orchestration.orchestrator import SalesOrchestrator
from app.orchestration.models import RouteDecision
from app.tools.registry import get_registered_tool


def _authorization(allowed_tables: set[str]) -> AuthorizationContext:
    return AuthorizationContext(
        user_id=1,
        auth_subject="auth0|tool-test",
        email="tool-test@example.com",
        role="analyst",
        allowed_tables=allowed_tables,
    )


def test_sales_performance_declares_every_physical_table_it_queries() -> None:
    tool = get_registered_tool("get_sales_performance")

    assert tool is not None
    assert tool.required_tables == {"Sales.SalesOrderHeader", "Sales.SalesTerritory"}


def test_tool_is_denied_before_execution_when_one_required_table_is_missing(monkeypatch) -> None:
    async def tool_route(_: str) -> RouteDecision:
        return RouteDecision(action="tool", tool_name="get_sales_performance", arguments={})

    def execution_must_not_run(*_args, **_kwargs):
        raise AssertionError("A denied tool must not execute SQL.")

    monkeypatch.setattr("app.orchestration.orchestrator.route_question", tool_route)
    monkeypatch.setattr("app.orchestration.orchestrator.execute_tool", execution_must_not_run)

    result = asyncio.run(
        SalesOrchestrator().handle(
            "Show sales performance",
            _authorization({"Sales.SalesOrderHeader"}),
        )
    )

    assert result.status == "error"
    assert result.message == "Tool table access was denied."
    assert result.metadata["unauthorized_tables"] == ["Sales.SalesTerritory"]


def test_tool_is_executed_when_all_required_tables_are_allowed(monkeypatch) -> None:
    async def tool_route(_: str) -> RouteDecision:
        return RouteDecision(action="tool", tool_name="get_sales_performance", arguments={})

    monkeypatch.setattr("app.orchestration.orchestrator.route_question", tool_route)
    monkeypatch.setattr(
        "app.orchestration.orchestrator.execute_tool",
        lambda *_args, **_kwargs: {"summary": {"revenue": 10}},
    )

    result = asyncio.run(
        SalesOrchestrator().handle(
            "Show sales performance",
            _authorization({"Sales.SalesOrderHeader", "Sales.SalesTerritory"}),
        )
    )

    assert result.status == "success"
    assert result.route == "tool"
