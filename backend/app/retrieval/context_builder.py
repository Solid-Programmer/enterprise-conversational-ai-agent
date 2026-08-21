"""Build bounded Text-to-SQL context from independent Qdrant retrievals."""

import json
from pathlib import Path
from typing import Any, Dict, List

from app.retrieval.retriever import retrieve_schema_context, retrieve_verified_queries


BUSINESS_RULES_PATH = Path(__file__).resolve().parent.parent / "sales" / "schema" / "sales_business_rules.json"


def _format_hits(title: str, hits: List[Dict[str, Any]]) -> str:
    blocks = [title]
    for hit in hits:
        payload = hit.get("payload", {})
        blocks.append(f"Score: {hit.get('score')}\n{payload.get('content') or json.dumps(payload, ensure_ascii=False)}")
    return "\n\n".join(blocks)


def build_text_to_sql_context(question: str) -> str:
    """Independently retrieve examples and schema context, then combine both with canonical rules."""
    verified_examples = retrieve_verified_queries(question, top_k=5)
    schema_chunks = retrieve_schema_context(question, top_k=8)
    rules = json.loads(BUSINESS_RULES_PATH.read_text(encoding="utf-8"))
    global_rules = rules.get("global_anti_hallucination_rules", [])
    return "\n\n".join([
        f"User question:\n{question}",
        _format_hits("Retrieved verified examples:", verified_examples),
        _format_hits("Retrieved semantic schema context:", schema_chunks),
        "Canonical global business rules:\n" + "\n".join(f"- {rule}" for rule in global_rules),
    ])
