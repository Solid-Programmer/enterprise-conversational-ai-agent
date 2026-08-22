from app.orchestration.models import RouteDecision
from app.orchestration import router


def test_hello_routes_to_chat() -> None:
    assert router.route_question("Hello").action == "chat"


def test_thanks_routes_to_chat() -> None:
    assert router.route_question("Thanks").action == "chat"


def test_capability_question_routes_to_chat() -> None:
    assert router.route_question("What can you do?").action == "chat"


def test_revenue_question_does_not_route_to_chat(monkeypatch) -> None:
    monkeypatch.setattr(router, "generate_structured", lambda **_: RouteDecision(action="text_to_sql"))
    assert router.route_question("Show revenue in 2012").action == "text_to_sql"


def test_ambiguous_business_question_routes_to_clarify(monkeypatch) -> None:
    monkeypatch.setattr(
        router,
        "generate_structured",
        lambda **_: RouteDecision(action="clarify", clarification_question="Best by which metric?"),
    )
    assert router.route_question("Show the best customers").action == "clarify"
