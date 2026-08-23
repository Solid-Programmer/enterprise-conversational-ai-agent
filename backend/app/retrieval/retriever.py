"""Shared-embedding runtime retrieval for SQL examples and schema context."""

import asyncio
from functools import lru_cache
from typing import Any, Dict, List, Sequence, Tuple

from app.core.config import settings
from app.core.execution import run_with_timeout
from app.observability.tracing import (
    compact_json,
    set_span_attributes,
    set_span_output,
    traced_span,
)
from app.retrieval.embeddings import OllamaEmbeddings
from app.retrieval.qdrant_store import (
    QdrantStore,
    SEMANTIC_SCHEMA_COLLECTION,
    VERIFIED_QUERIES_COLLECTION,
)


@lru_cache(maxsize=1)
def get_embedding_client() -> OllamaEmbeddings:
    """Return one reusable Ollama embedding client for the process."""
    return OllamaEmbeddings()


@lru_cache(maxsize=1)
def get_verified_queries_store() -> QdrantStore:
    """Return one reusable client for the verified-query collection."""
    return QdrantStore(VERIFIED_QUERIES_COLLECTION)


@lru_cache(maxsize=1)
def get_semantic_schema_store() -> QdrantStore:
    """Return one reusable client for the semantic-schema collection."""
    return QdrantStore(SEMANTIC_SCHEMA_COLLECTION)


def warm_retrieval_clients() -> None:
    """Eagerly establish both Qdrant client paths during application startup."""
    get_verified_queries_store().client.collection_exists(VERIFIED_QUERIES_COLLECTION)
    get_semantic_schema_store().client.collection_exists(SEMANTIC_SCHEMA_COLLECTION)


def close_retrieval_clients() -> None:
    """Release cached HTTP transports during application shutdown."""
    get_embedding_client().close()
    get_verified_queries_store().client.close()
    get_semantic_schema_store().client.close()
    get_embedding_client.cache_clear()
    get_verified_queries_store.cache_clear()
    get_semantic_schema_store.cache_clear()


def _require_question(question: str) -> None:
    if not question.strip():
        raise ValueError("Question must not be empty.")


async def embed_retrieval_query(question: str) -> List[float]:
    """Embed one user question once for reuse across retrieval collections."""
    _require_question(question)
    with traced_span(
        "retrieval.query_embedding",
        {"embedding.model": settings.OLLAMA_EMBED_MODEL},
        span_kind="EMBEDDING",
        input_value=question,
    ) as span:
        vector = await run_with_timeout(
            asyncio.to_thread(get_embedding_client().embed_query, question),
            timeout_seconds=settings.RETRIEVAL_TIMEOUT_SECONDS,
            stage="retrieval.query_embedding",
        )
        set_span_attributes(span, {"embedding.vector_size": len(vector)})
        set_span_output(
            span,
            {"vector_size": len(vector)},
            mime_type="application/json",
        )
        return vector


async def search_verified_queries(
    question: str,
    vector: Sequence[float],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Search verified examples with a caller-provided query embedding."""
    with traced_span(
        "retrieval.verified_queries",
        {"retrieval.top_k": top_k},
        span_kind="RETRIEVER",
        input_value=question,
    ) as span:
        results = await run_with_timeout(
            asyncio.to_thread(
                get_verified_queries_store().search,
                vector,
                limit=top_k,
            ),
            timeout_seconds=settings.RETRIEVAL_TIMEOUT_SECONDS,
            stage="retrieval.verified_queries",
        )
        summary = [
            {
                "id": hit["payload"].get("id", hit["id"]),
                "score": hit["score"],
                "question": hit["payload"].get("question", "")[:200],
            }
            for hit in results
        ]
        set_span_attributes(
            span,
            {
                "retrieval.result_count": len(results),
                "retrieval.top_score": results[0]["score"] if results else None,
                "retrieval.results": compact_json(summary),
            },
        )
        set_span_output(span, summary, mime_type="application/json")
        return results


async def search_schema_context(
    question: str,
    vector: Sequence[float],
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    """Search semantic schema context with a caller-provided query embedding."""
    with traced_span(
        "retrieval.semantic_schema",
        {"retrieval.top_k": top_k},
        span_kind="RETRIEVER",
        input_value=question,
    ) as span:
        results = await run_with_timeout(
            asyncio.to_thread(
                get_semantic_schema_store().search,
                vector,
                limit=top_k,
            ),
            timeout_seconds=settings.RETRIEVAL_TIMEOUT_SECONDS,
            stage="retrieval.semantic_schema",
        )
        summary = [
            {
                "id": hit["id"],
                "score": hit["score"],
                "type": hit["payload"].get("type"),
                "table": hit["payload"].get("table"),
                "qualified_name": hit["payload"].get("qualified_name"),
            }
            for hit in results
        ]
        set_span_attributes(
            span,
            {
                "retrieval.result_count": len(results),
                "retrieval.top_score": results[0]["score"] if results else None,
                "retrieval.results": compact_json(summary),
            },
        )
        set_span_output(span, summary, mime_type="application/json")
        return results


async def retrieve_text_to_sql_context(
    question: str,
    verified_top_k: int = 5,
    schema_top_k: int = 8,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Embed once, then search both Qdrant collections concurrently."""
    vector = await embed_retrieval_query(question)
    verified_examples, schema_chunks = await asyncio.gather(
        search_verified_queries(question, vector, top_k=verified_top_k),
        search_schema_context(question, vector, top_k=schema_top_k),
    )
    return verified_examples, schema_chunks


async def retrieve_verified_queries(
    question: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Retrieve verified examples when only that collection is needed."""
    vector = await embed_retrieval_query(question)
    return await search_verified_queries(question, vector, top_k=top_k)


async def retrieve_schema_context(
    question: str,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    """Retrieve semantic schema context when only that collection is needed."""
    vector = await embed_retrieval_query(question)
    return await search_schema_context(question, vector, top_k=top_k)
