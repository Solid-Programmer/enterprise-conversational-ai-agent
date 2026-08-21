"""Structured Qwen/Ollama calls used by routing, SQL generation, and repair."""

import json
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from ollama import Client
from pydantic import BaseModel

from app.core.config import settings
from app.observability.tracing import set_span_attributes, set_span_output, traced_span
from app.orchestration.models import SQLGeneration


T = TypeVar("T", bound=BaseModel)
MODEL_NAME = "qwen2.5:7b"
_client: Optional[Client] = None

TEXT_TO_SQL_SYSTEM_PROMPT = """You generate one Microsoft SQL Server T-SQL query.
Return only the supplied JSON schema. The value of sql must be a single SELECT statement, or null.
Use only the supplied context. Use fully qualified table names. Use TOP, never LIMIT.
Do not produce prose, DDL, DML, EXEC, stored procedures, comments, or multiple statements."""


def get_ollama_client() -> Client:
    """Return one reusable Ollama client for the process."""
    global _client
    if _client is None:
        _client = Client(host=settings.OLLAMA_BASE_URL)
    return _client


def generate_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: Type[T],
    temperature: int = 0,
    operation_name: str = "llm.generate",
    trace_attributes: Optional[Dict[str, Any]] = None,
    result_attributes: Optional[Callable[[T], Dict[str, Any]]] = None,
) -> T:
    """Call Ollama chat with a Pydantic JSON schema and parse its structured response."""
    attributes = {
        "llm.model_name": MODEL_NAME,
        "llm.provider": "ollama",
        **(trace_attributes or {}),
    }
    with traced_span(
        operation_name,
        attributes,
        span_kind="LLM",
        input_value=user_prompt[:4000],
    ) as span:
        body = get_ollama_client().chat(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            format=response_model.model_json_schema(),
            stream=False,
            options={"temperature": temperature},
        )
        content = body["message"]["content"]
        token_attributes = {
            "llm.token_count.prompt": body.get("prompt_eval_count"),
            "llm.token_count.completion": body.get("eval_count"),
            "llm.token_count.total": (
                body["prompt_eval_count"] + body["eval_count"]
                if body.get("prompt_eval_count") is not None and body.get("eval_count") is not None
                else None
            ),
        }
        set_span_attributes(span, token_attributes)
        result = response_model.model_validate(json.loads(content))
        set_span_output(span, content, mime_type="application/json")
        if result_attributes:
            set_span_attributes(span, result_attributes(result))
        return result


def generate_text_to_sql(question: str, context: str) -> SQLGeneration:
    """Generate a schema-constrained SQL response without validation or execution."""
    return generate_structured(
        system_prompt=TEXT_TO_SQL_SYSTEM_PROMPT,
        user_prompt=f"User question:\n{question}\n\nRetrieval context:\n{context}",
        response_model=SQLGeneration,
        temperature=0,
        operation_name="text_to_sql.generate",
        trace_attributes={"text_to_sql.question": question},
        result_attributes=lambda result: {
            "text_to_sql.sql": result.sql,
            "text_to_sql.returned_sql": result.sql is not None,
        },
    )
