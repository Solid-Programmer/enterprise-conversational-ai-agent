"""Grounded, concise natural-language answers for successful trusted results."""

from typing import Any, Optional

from pydantic import BaseModel

from app.llm.qwen_client import generate_structured
from app.observability.tracing import compact_json, result_summary
from app.prompts import load_prompt, render_prompt


class AnswerGeneration(BaseModel):
    """Structured response returned by the answer-generation model call."""

    answer: str


def generate_answer(question: str, data: Any, sql: Optional[str]) -> AnswerGeneration:
    """Generate an answer grounded in a bounded preview of trusted tool/SQL output."""
    preview = result_summary(data)
    return generate_structured(
        system_prompt=load_prompt("answer_generation_system_v1.txt"),
        user_prompt=render_prompt(
            "answer_generation_user_v1.txt",
            question=question,
            sql=sql or "No SQL was generated; a deterministic tool produced the result.",
            data_preview=compact_json(preview),
        ),
        response_model=AnswerGeneration,
        temperature=0,
        max_output_tokens=400,
        operation_name="answer.generate",
        trace_attributes={"answer.has_sql": sql is not None, **preview},
        result_attributes=lambda result: {"answer.text": result.answer},
    )
