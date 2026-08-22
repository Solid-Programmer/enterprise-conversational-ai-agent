from app.db.sql_executor import execute_validated_sql
from app.db.sql_validator import SQLValidationResult
from app.llm.answer_generator import AnswerGeneration, generate_answer


class _Cursor:
    description = [
        ("CardNumber",),
        ("ExpMonth",),
        ("ExpYear",),
        ("CreditCardApprovalCode",),
        ("AccountNumber",),
    ]

    def execute(self, sql: str, params: tuple) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self):
        return [("4111111111111111", 12, 2028, "ABC123XYZ", "AW00000001")]


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cursor_instance

    def close(self) -> None:
        pass


def test_execution_returns_masked_data_for_downstream_answer_generation(monkeypatch) -> None:
    monkeypatch.setattr("app.db.sql_executor.get_db_connection", lambda: _Connection())

    result = execute_validated_sql(SQLValidationResult(valid=True, normalized_sql="SELECT 1"))

    assert result == [{
        "CardNumber": "************1111",
        "ExpMonth": "**",
        "ExpYear": "****",
        "CreditCardApprovalCode": "*********",
        "AccountNumber": "AW00000001",
    }]


def test_answer_generation_receives_the_masked_execution_result(monkeypatch) -> None:
    monkeypatch.setattr("app.db.sql_executor.get_db_connection", lambda: _Connection())
    captured = {}

    async def fake_generate_structured(**kwargs):
        captured["user_prompt"] = kwargs["user_prompt"]
        return AnswerGeneration(answer="Safe answer")

    monkeypatch.setattr("app.llm.answer_generator.generate_structured", fake_generate_structured)
    safe_result = execute_validated_sql(SQLValidationResult(valid=True, normalized_sql="SELECT 1"))

    asyncio.run(generate_answer("Show card details", safe_result, "SELECT 1"))

    assert "4111111111111111" not in captured["user_prompt"]
    assert "************1111" in captured["user_prompt"]
import asyncio
