"""Independent runtime retrieval functions for SQL examples and schema context."""

import asyncio
from typing import Any, Dict, List

from app.retrieval.embeddings import OllamaEmbeddings
from app.retrieval.qdrant_store import (
    QdrantStore,
    SEMANTIC_SCHEMA_COLLECTION,
    VERIFIED_QUERIES_COLLECTION,
)
from app.observability.tracing import compact_json, set_span_attributes, set_span_output, traced_span
from app.core.config import settings
from app.core.execution import run_with_timeout


def _retrieve_verified_queries(question: str, top_k: int) -> List[Dict[str, Any]]:
    vector = OllamaEmbeddings().embed_query(question)
    return QdrantStore(VERIFIED_QUERIES_COLLECTION).search(vector, limit=top_k)


async def retrieve_verified_queries(question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Retrieve similar validated NL-to-SQL examples, including SQL and source metadata."""
    if not question.strip():
        raise ValueError("Question must not be empty.")
    with traced_span("retrieval.verified_queries", {
        "retrieval.top_k": top_k,
        "embedding.model": "nomic-embed-text",
    }, span_kind="RETRIEVER", input_value=question) as span:
        results = await run_with_timeout(
            asyncio.to_thread(_retrieve_verified_queries, question, top_k),
            timeout_seconds=settings.RETRIEVAL_TIMEOUT_SECONDS,
            stage="retrieval.verified_queries",
        )
        summary = [{
            "id": hit["payload"].get("id", hit["id"]),
            "score": hit["score"],
            "question": hit["payload"].get("question", "")[:200],
        } for hit in results]
        set_span_attributes(span, {
            "retrieval.result_count": len(results),
            "retrieval.top_score": results[0]["score"] if results else None,
            "retrieval.results": compact_json(summary),
        })
        set_span_output(span, summary, mime_type="application/json")
        return results


def _retrieve_schema_context(question: str, top_k: int) -> List[Dict[str, Any]]:
    vector = OllamaEmbeddings().embed_query(question)
    return QdrantStore(SEMANTIC_SCHEMA_COLLECTION).search(vector, limit=top_k)


async def retrieve_schema_context(question: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """Retrieve relevant semantic tables, metrics, relationships, and business-rule chunks."""
    if not question.strip():
        raise ValueError("Question must not be empty.")
    with traced_span("retrieval.semantic_schema", {
        "retrieval.top_k": top_k,
        "embedding.model": "nomic-embed-text",
    }, span_kind="RETRIEVER", input_value=question) as span:
        results = await run_with_timeout(
            asyncio.to_thread(_retrieve_schema_context, question, top_k),
            timeout_seconds=settings.RETRIEVAL_TIMEOUT_SECONDS,
            stage="retrieval.semantic_schema",
        )
        summary = [{
            "id": hit["id"],
            "score": hit["score"],
            "type": hit["payload"].get("type"),
            "table": hit["payload"].get("table"),
            "qualified_name": hit["payload"].get("qualified_name"),
        } for hit in results]
        set_span_attributes(span, {
            "retrieval.result_count": len(results),
            "retrieval.top_score": results[0]["score"] if results else None,
            "retrieval.results": compact_json(summary),
        })
        set_span_output(span, summary, mime_type="application/json")
        return results
