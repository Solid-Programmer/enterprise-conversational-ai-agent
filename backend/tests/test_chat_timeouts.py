import asyncio

from fastapi.responses import JSONResponse
import pytest
from starlette.requests import Request

from app.api import chat as chat_api
from app.auth.rbac import AuthorizationContext
from app.core.execution import StageTimeoutError
from app.orchestration import orchestrator


AUTHORIZATION = AuthorizationContext(
    user_id=1,
    auth_subject="auth0|test",
    email="test@example.com",
    role="User",
    allowed_tables={"Sales.SalesOrderHeader"},
)


def test_router_timeout_returns_controlled_gateway_timeout(monkeypatch) -> None:
    async def timed_out_handle(*_args, **_kwargs):
        raise StageTimeoutError("router.decide", 15)

    monkeypatch.setattr(chat_api._orchestrator, "handle", timed_out_handle)
    request = Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})
    response = asyncio.run(
        chat_api.chat(chat_api.ChatRequest(message="Show revenue"), http_request=request, authorization=AUTHORIZATION)
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 504
    assert b"took too long" in response.body


def test_text_to_sql_timeout_does_not_execute_repair_or_escalate(monkeypatch) -> None:
    calls = {"execute": 0, "repair": 0}

    async def build_context(*_args):
        return "context"

    class TimedOutGenerator:
        async def generate_sql(self, *_args):
            raise StageTimeoutError("text_to_sql.generate", 30)

    async def execute(*_args):
        calls["execute"] += 1

    async def repair(*_args):
        calls["repair"] += 1

    monkeypatch.setattr(orchestrator, "build_text_to_sql_context", build_context)
    monkeypatch.setattr(orchestrator, "TextToSQLGenerator", TimedOutGenerator)
    monkeypatch.setattr(orchestrator, "execute_validated_sql_with_timeout", execute)
    monkeypatch.setattr(orchestrator, "repair_sql", repair)

    with pytest.raises(StageTimeoutError):
        asyncio.run(orchestrator.SalesOrchestrator()._run_text_to_sql("Show revenue", AUTHORIZATION))

    assert calls == {"execute": 0, "repair": 0}
