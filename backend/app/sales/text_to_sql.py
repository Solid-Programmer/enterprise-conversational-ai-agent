"""Sales-domain adapter for structured Text-to-SQL generation."""

from app.llm.qwen_client import generate_text_to_sql
from app.orchestration.models import SQLGeneration


class TextToSQLGenerator:
    """Generate structured SQL from a caller-provided, retrieval-built Sales context."""

    def generate_sql(self, user_prompt: str, context: str) -> SQLGeneration:
        return generate_text_to_sql(user_prompt, context)
