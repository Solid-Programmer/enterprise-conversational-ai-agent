"""Independent runtime retrieval functions for SQL examples and schema context."""

from typing import Any, Dict, List

from app.retrieval.embeddings import OllamaEmbeddings
from app.retrieval.qdrant_store import (
    QdrantStore,
    SEMANTIC_SCHEMA_COLLECTION,
    VERIFIED_QUERIES_COLLECTION,
)
from app.observability.tracing import compact_json, set_span_attributes, set_span_output, traced_span


def retrieve_verified_queries(question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Retrieve similar validated NL-to-SQL examples, including SQL and source metadata."""
    if not question.strip():
        raise ValueError("Question must not be empty.")
    with traced_span("retrieval.verified_queries", {
        "retrieval.top_k": top_k,
        "embedding.model": "nomic-embed-text",
    }, span_kind="RETRIEVER", input_value=question) as span:
        vector = OllamaEmbeddings().embed_query(question)
        results = QdrantStore(VERIFIED_QUERIES_COLLECTION).search(vector, limit=top_k)
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


def retrieve_schema_context(question: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """Retrieve relevant semantic tables, metrics, relationships, and business-rule chunks."""
    if not question.strip():
        raise ValueError("Question must not be empty.")
    with traced_span("retrieval.semantic_schema", {
        "retrieval.top_k": top_k,
        "embedding.model": "nomic-embed-text",
    }, span_kind="RETRIEVER", input_value=question) as span:
        vector = OllamaEmbeddings().embed_query(question)
        results = QdrantStore(SEMANTIC_SCHEMA_COLLECTION).search(vector, limit=top_k)
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
