"""Granular end-to-end latency benchmarks for the revenue-in-2013 query.

The mocked test is safe for the normal unit-test suite. The live test exercises
the real FastAPI boundary, SQL-backed RBAC, Ollama, Qdrant, SQL validation and
authorization, SQL Server, answer generation, and response serialization.
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from functools import wraps
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Coroutine, TypeVar

import pytest
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.auth import auth0, rbac
from app.auth.auth0 import AuthenticatedUser, get_current_user
from app.auth.rbac import AuthorizationContext
from app.db import sql_executor, sql_validator
from app.db.connection import get_db_connection
from app.llm import answer_generator, qwen_client
from app.llm.answer_generator import AnswerGeneration
from app.main import app
from app.orchestration import orchestrator, router
from app.orchestration.models import RouteDecision, SQLGeneration
from app.retrieval import context_builder, retriever
from app.sales import text_to_sql


QUERY = "Please Provide total revenue in 2013"
REPORT_PATH = (
    Path(__file__).resolve().parents[2]
    / "test"
    / "results"
    / "e2e_revenue_2013_performance.json"
)
T = TypeVar("T")


class TimingRecorder:
    """Collect repeated sync/async call durations without changing production code."""

    def __init__(self) -> None:
        self.samples: dict[str, list[float]] = defaultdict(list)

    def record(self, name: str, started: float) -> None:
        self.samples[name].append((time.perf_counter() - started) * 1000)

    def wrap_sync(self, name: str, function: Callable[..., T]) -> Callable[..., T]:
        @wraps(function)
        def measured(*args: Any, **kwargs: Any) -> T:
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                self.record(name, started)

        return measured

    def wrap_async(
        self,
        name: str,
        function: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(function)
        async def measured(*args: Any, **kwargs: Any) -> T:
            started = time.perf_counter()
            try:
                return await function(*args, **kwargs)
            finally:
                self.record(name, started)

        return measured

    def total(self, name: str) -> float:
        return sum(self.samples.get(name, []))

    def report(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "total_ms": round(sum(values), 2),
                "calls": len(values),
                "samples_ms": [round(value, 2) for value in values],
            }
            for name, values in self.samples.items()
        }


def _find_live_auth_subject() -> str:
    """Find a mapped active user allowed to query SalesOrderHeader.

    The subject is used only to exercise the normal RBAC dependency and is
    intentionally never included in the generated performance report.
    """
    configured_subject = os.getenv("E2E_AUTH_SUBJECT", "").strip()
    if configured_subject:
        return configured_subject

    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT TOP (1)
                u.AuthSubject
            FROM rbac.AppUsers AS u
            JOIN rbac.UserRoles AS ur
                ON ur.UserId = u.UserId
            JOIN rbac.RoleTablePermissions AS rtp
                ON rtp.RoleId = ur.RoleId
            WHERE u.IsActive = 1
              AND rtp.SchemaName = 'Sales'
              AND rtp.TableName = 'SalesOrderHeader'
            ORDER BY u.UserId;
            """
        )
        row = cursor.fetchone()
    finally:
        connection.close()

    if row is None:
        raise AssertionError(
            "No active RBAC user can access Sales.SalesOrderHeader. "
            "Set E2E_AUTH_SUBJECT or seed the RBAC tables."
        )
    return str(row.AuthSubject)


def _install_timing_wrappers(monkeypatch: Any, timings: TimingRecorder) -> None:
    """Measure the exact call sites used by the production HTTP flow."""
    monkeypatch.setattr(
        rbac,
        "get_db_connection",
        timings.wrap_sync("rbac_db_connection", rbac.get_db_connection),
    )
    monkeypatch.setattr(
        rbac,
        "load_authorization_context",
        timings.wrap_sync("rbac_context_lookup", rbac.load_authorization_context),
    )
    monkeypatch.setattr(
        qwen_client.AsyncClient,
        "chat",
        timings.wrap_async("ollama_chat_request", qwen_client.AsyncClient.chat),
    )
    monkeypatch.setattr(
        orchestrator,
        "route_question",
        timings.wrap_async("router_decision", orchestrator.route_question),
    )
    monkeypatch.setattr(
        retriever,
        "search_verified_queries",
        timings.wrap_async(
            "retrieval_verified_queries",
            retriever.search_verified_queries,
        ),
    )
    monkeypatch.setattr(
        retriever,
        "search_schema_context",
        timings.wrap_async(
            "retrieval_semantic_schema",
            retriever.search_schema_context,
        ),
    )
    monkeypatch.setattr(
        retriever.OllamaEmbeddings,
        "__init__",
        timings.wrap_sync(
            "ollama_embeddings_client_initialization",
            retriever.OllamaEmbeddings.__init__,
        ),
    )
    monkeypatch.setattr(
        retriever.OllamaEmbeddings,
        "embed_query",
        timings.wrap_sync(
            "ollama_query_embedding",
            retriever.OllamaEmbeddings.embed_query,
        ),
    )
    monkeypatch.setattr(
        retriever.QdrantStore,
        "__init__",
        timings.wrap_sync(
            "qdrant_client_initialization",
            retriever.QdrantStore.__init__,
        ),
    )
    monkeypatch.setattr(
        retriever.QdrantStore,
        "search",
        timings.wrap_sync(
            "qdrant_vector_search",
            retriever.QdrantStore.search,
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "build_text_to_sql_context",
        timings.wrap_async(
            "context_build_total",
            orchestrator.build_text_to_sql_context,
        ),
    )
    monkeypatch.setattr(
        orchestrator.TextToSQLGenerator,
        "generate_sql",
        timings.wrap_async(
            "sql_generation",
            orchestrator.TextToSQLGenerator.generate_sql,
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "validate_sql",
        timings.wrap_sync("sql_validation", orchestrator.validate_sql),
    )
    monkeypatch.setattr(
        orchestrator,
        "authorize_sql_tables",
        timings.wrap_sync(
            "sql_table_authorization",
            orchestrator.authorize_sql_tables,
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "execute_validated_sql_with_timeout",
        timings.wrap_async(
            "sql_execution",
            orchestrator.execute_validated_sql_with_timeout,
        ),
    )
    monkeypatch.setattr(
        sql_executor,
        "get_db_connection",
        timings.wrap_sync(
            "sql_db_connection",
            sql_executor.get_db_connection,
        ),
    )
    original_mask_sensitive_result = sql_executor.mask_sensitive_result
    masking_depth = 0

    @wraps(original_mask_sensitive_result)
    def timed_mask_sensitive_result(*args: Any, **kwargs: Any) -> Any:
        nonlocal masking_depth
        if masking_depth:
            return original_mask_sensitive_result(*args, **kwargs)
        masking_depth += 1
        started = time.perf_counter()
        try:
            return original_mask_sensitive_result(*args, **kwargs)
        finally:
            timings.record("result_masking", started)
            masking_depth -= 1

    monkeypatch.setattr(
        sql_executor,
        "mask_sensitive_result",
        timed_mask_sensitive_result,
    )
    monkeypatch.setattr(
        orchestrator,
        "repair_sql",
        timings.wrap_async("sql_repair", orchestrator.repair_sql),
    )
    monkeypatch.setattr(
        chat_api._orchestrator,
        "handle",
        timings.wrap_async(
            "orchestrator_handle",
            chat_api._orchestrator.handle,
        ),
    )
    monkeypatch.setattr(
        chat_api,
        "generate_answer",
        timings.wrap_async("answer_generation", chat_api.generate_answer),
    )


def _derived_timings(timings: TimingRecorder) -> dict[str, float]:
    """Calculate non-overlapping overhead while respecting parallel retrieval."""
    qdrant_search_critical_path = max(
        timings.total("retrieval_verified_queries"),
        timings.total("retrieval_semantic_schema"),
    )
    retrieval_critical_path = timings.total("context_build_total")
    context_assembly = max(
        retrieval_critical_path
        - timings.total("ollama_embeddings_client_initialization")
        - timings.total("ollama_query_embedding")
        - qdrant_search_critical_path,
        0,
    )
    known_orchestrator_work = sum(
        timings.total(name)
        for name in (
            "router_decision",
            "context_build_total",
            "sql_generation",
            "sql_validation",
            "sql_table_authorization",
            "sql_execution",
            "sql_repair",
        )
    )
    orchestrator_overhead = max(
        timings.total("orchestrator_handle") - known_orchestrator_work,
        0,
    )
    http_overhead = max(
        timings.total("http_total")
        - timings.total("auth0_token_validation")
        - timings.total("rbac_context_lookup")
        - timings.total("orchestrator_handle")
        - timings.total("answer_generation"),
        0,
    )
    rbac_query_and_mapping = max(
        timings.total("rbac_context_lookup")
        - timings.total("rbac_db_connection"),
        0,
    )
    sql_query_fetch_normalize = max(
        timings.total("sql_execution")
        - timings.total("sql_db_connection")
        - timings.total("result_masking"),
        0,
    )
    llm_stage_total = sum(
        timings.total(name)
        for name in (
            "router_decision",
            "sql_generation",
            "sql_repair",
            "answer_generation",
        )
    )
    structured_llm_overhead = max(
        llm_stage_total - timings.total("ollama_chat_request"),
        0,
    )
    return {
        "retrieval_parallel_critical_path_ms": round(retrieval_critical_path, 2),
        "qdrant_parallel_search_critical_path_ms": round(
            qdrant_search_critical_path,
            2,
        ),
        "context_assembly_overhead_ms": round(context_assembly, 2),
        "rbac_queries_and_mapping_ms": round(rbac_query_and_mapping, 2),
        "sql_query_fetch_normalize_ms": round(sql_query_fetch_normalize, 2),
        "serial_llm_stage_total_ms": round(llm_stage_total, 2),
        "structured_prompt_parse_trace_overhead_ms": round(
            structured_llm_overhead,
            2,
        ),
        "orchestrator_unattributed_overhead_ms": round(orchestrator_overhead, 2),
        "http_auth_validation_serialization_overhead_ms": round(http_overhead, 2),
    }


def _print_report(report: dict[str, Any]) -> None:
    print("\n" + "=" * 94)
    print("LIVE END-TO-END PERFORMANCE BREAKDOWN")
    print(f"Query: {report['query']}")
    print(f"Authentication mode: {report['authentication_mode']}")
    print("Nested component rows overlap their parent stage; derived rows avoid double counting.")
    print("-" * 94)
    print(f"{'Component':<48} {'Calls':>7} {'Total ms':>14} {'Total s':>12}")
    print("-" * 94)
    for name, measurement in report["timings"].items():
        total_ms = measurement["total_ms"]
        print(
            f"{name:<48} {measurement['calls']:>7} "
            f"{total_ms:>14.2f} {total_ms / 1000:>12.3f}"
        )
    print("-" * 94)
    for name, value in report["derived_timings"].items():
        print(f"{name:<56} {value:>14.2f} ms")
    print("-" * 94)
    print(f"Route: {report['response']['route']}")
    print(f"SQL: {report['response']['sql']}")
    print(f"Data: {json.dumps(report['response']['data'], ensure_ascii=False)}")
    print(f"Answer: {report['response']['answer']}")
    print(f"Report: {REPORT_PATH}")
    print("=" * 94)


def test_e2e_revenue_2013_mocked_timing(monkeypatch) -> None:
    """Fast component-level benchmark with mocked network and database calls."""
    query = QUERY
    auth = AuthorizationContext(
        user_id=1,
        auth_subject="test-user",
        email="test@example.com",
        role="Sales_Analyst",
        allowed_tables={"Sales.SalesOrderHeader", "Sales.SalesOrderDetail"},
    )

    async def _run_mocked() -> None:
        step_timings: dict[str, float] = {}
        overall_start = time.perf_counter()

        async def mock_route_question(_: str) -> RouteDecision:
            await asyncio.sleep(0.01)
            return RouteDecision(
                action="text_to_sql",
                reason="Requires Sales database query.",
            )

        monkeypatch.setattr(router, "route_question", mock_route_question)
        started = time.perf_counter()
        route_decision = await router.route_question(query)
        step_timings["router"] = (time.perf_counter() - started) * 1000

        async def mock_build_context(_: str) -> str:
            await asyncio.sleep(0.015)
            return (
                "User question:\nPlease Provide total revenue in 2013\n\n"
                "Schema:\nSales.SalesOrderHeader(SubTotal, OrderDate)"
            )

        monkeypatch.setattr(context_builder, "build_text_to_sql_context", mock_build_context)
        started = time.perf_counter()
        context = await context_builder.build_text_to_sql_context(query)
        step_timings["context"] = (time.perf_counter() - started) * 1000

        async def mock_generate_sql(_: Any, __: str, ___: str) -> SQLGeneration:
            await asyncio.sleep(0.02)
            return SQLGeneration(
                sql=(
                    "SELECT SUM(SubTotal) AS TotalRevenue "
                    "FROM Sales.SalesOrderHeader WHERE YEAR(OrderDate) = 2013"
                )
            )

        monkeypatch.setattr(text_to_sql.TextToSQLGenerator, "generate_sql", mock_generate_sql)
        generated_sql = await text_to_sql.TextToSQLGenerator().generate_sql(query, context)
        validation = sql_validator.validate_sql(generated_sql.sql or "")
        authorization_result = sql_validator.authorize_sql_tables(
            validation.normalized_sql or "",
            auth.allowed_tables,
            role=auth.role,
        )

        async def mock_execute_sql(*_: Any, **__: Any) -> list[dict[str, float]]:
            await asyncio.sleep(0.01)
            return [{"TotalRevenue": 43622479.0537}]

        monkeypatch.setattr(
            sql_executor,
            "execute_validated_sql_with_timeout",
            mock_execute_sql,
        )
        data = await sql_executor.execute_validated_sql_with_timeout(validation)

        async def mock_generate_answer(*_: Any, **__: Any) -> AnswerGeneration:
            await asyncio.sleep(0.01)
            return AnswerGeneration(
                answer="The total revenue in 2013 was $43,622,479.05."
            )

        monkeypatch.setattr(answer_generator, "generate_answer", mock_generate_answer)
        answer = await answer_generator.generate_answer(query, data, generated_sql.sql)

        assert route_decision.action == "text_to_sql"
        assert validation.valid is True
        assert authorization_result.authorized is True
        assert answer.answer
        assert step_timings["router"] > 0
        assert step_timings["context"] > 0
        assert (time.perf_counter() - overall_start) * 1000 > 0

    asyncio.run(_run_mocked())


@pytest.mark.live
def test_e2e_revenue_2013_live_timing_breakdown(monkeypatch) -> None:
    """Benchmark the real application path and persist a machine-readable report."""
    timings = TimingRecorder()
    _install_timing_wrappers(monkeypatch, timings)

    access_token = os.getenv("E2E_AUTH0_ACCESS_TOKEN", "").strip()
    headers: dict[str, str] = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

        def timed_current_user(
            credentials: HTTPAuthorizationCredentials | None = Depends(
                auth0._bearer_scheme
            ),
        ) -> AuthenticatedUser:
            measured = timings.wrap_sync(
                "auth0_token_validation",
                auth0.get_current_user,
            )
            return measured(credentials)

        app.dependency_overrides[get_current_user] = timed_current_user
        authentication_mode = "real Auth0 access-token verification"
    else:
        auth_subject = _find_live_auth_subject()
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            sub=auth_subject
        )
        authentication_mode = (
            "Auth0 identity override; real SQL-backed RBAC still measured"
        )

    try:
        with TestClient(app) as client:
            started = time.perf_counter()
            response = client.post(
                "/api/chat",
                headers=headers,
                json={"message": QUERY},
            )
            timings.record("http_total", started)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    payload = response.json()
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "query": QUERY,
        "authentication_mode": authentication_mode,
        "http_status_code": response.status_code,
        "timings": timings.report(),
        "derived_timings": _derived_timings(timings),
        "response": {
            "status": payload.get("status"),
            "route": payload.get("route"),
            "tool_name": payload.get("tool_name"),
            "sql": payload.get("sql"),
            "answer": payload.get("answer"),
            "data": payload.get("data"),
            "message": payload.get("message"),
            "metadata": payload.get("metadata"),
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _print_report(report)

    assert response.status_code == 200, payload
    assert payload["status"] == "success", payload
    assert payload["route"] == "text_to_sql", payload
    assert payload["sql"], payload
    assert payload["data"], payload
    assert payload["answer"], payload
    assert timings.total("rbac_context_lookup") > 0
    assert timings.total("router_decision") > 0
    assert timings.total("context_build_total") > 0
    assert timings.total("sql_generation") > 0
    assert timings.total("sql_validation") > 0
    assert timings.total("sql_table_authorization") > 0
    assert timings.total("sql_execution") > 0
    assert timings.total("answer_generation") > 0
    assert timings.total("http_total") > 0
