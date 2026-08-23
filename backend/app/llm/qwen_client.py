"""Structured Qwen/Ollama calls used by routing, SQL generation, and repair."""

import json
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from ollama import AsyncClient
from pydantic import BaseModel

from app.core.config import settings
from app.core.execution import run_with_timeout
from app.observability.tracing import set_span_attributes, set_span_output, traced_span
from app.orchestration.models import SQLGeneration
from app.prompts import load_prompt, render_prompt


T = TypeVar("T", bound=BaseModel)
MODEL_NAME = "qwen2.5:7b"
_client: Optional[AsyncClient] = None

def get_ollama_client() -> AsyncClient:
    """Return one reusable Ollama client for the process."""
    global _client
    if _client is None:
        _client = AsyncClient(host=settings.OLLAMA_BASE_URL)
    return _client


async def generate_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: Type[T],
    temperature: int = 0,
    max_output_tokens: Optional[int] = None,
    operation_name: str = "llm.generate",
    timeout_seconds: float = 30,
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
        options: Dict[str, Any] = {"temperature": temperature}
        if max_output_tokens is not None:
            options["num_predict"] = max_output_tokens
        body = await run_with_timeout(
            get_ollama_client().chat(
                model=MODEL_NAME,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                format=response_model.model_json_schema(),
                stream=False,
                keep_alive=settings.OLLAMA_KEEP_ALIVE,
                options=options,
            ),
            timeout_seconds=timeout_seconds,
            stage=operation_name,
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


async def warm_generation_model() -> None:
    """Load the generation model and request the configured Ollama residency."""
    await run_with_timeout(
        get_ollama_client().generate(
            model=MODEL_NAME,
            prompt="",
            stream=False,
            keep_alive=settings.OLLAMA_KEEP_ALIVE,
            options={"num_predict": 0},
        ),
        timeout_seconds=settings.WARMUP_TIMEOUT_SECONDS,
        stage="runtime.warm_generation_model",
    )


async def close_ollama_client() -> None:
    """Release the process-scoped asynchronous transport at shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def generate_text_to_sql(question: str, context: str) -> SQLGeneration:
    """Generate a schema-constrained SQL response without validation or execution."""
    return await generate_structured(
        system_prompt=load_prompt("text_to_sql_system_v1.txt"),
        user_prompt=render_prompt("text_to_sql_user_v1.txt", question=question, context=context),
        response_model=SQLGeneration,
        temperature=0,
        max_output_tokens=500,
        operation_name="text_to_sql.generate",
        timeout_seconds=settings.TEXT_TO_SQL_TIMEOUT_SECONDS,
        trace_attributes={"text_to_sql.question": question},
        result_attributes=lambda result: {
            "text_to_sql.sql": result.sql,
            "text_to_sql.returned_sql": result.sql is not None,
        },
    )
