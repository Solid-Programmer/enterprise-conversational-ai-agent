import asyncio
from typing import Any, Sequence

from app.retrieval import retriever


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def embed_query(self, question: str) -> list[float]:
        self.questions.append(question)
        return [0.1, 0.2, 0.3]


class _FakeStore:
    def __init__(self, result: list[dict[str, Any]]) -> None:
        self.result = result
        self.searches: list[tuple[Sequence[float], int]] = []

    def search(
        self,
        vector: Sequence[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        self.searches.append((vector, limit))
        return self.result


def test_combined_retrieval_embeds_once_and_searches_both_collections(
    monkeypatch,
) -> None:
    embeddings = _FakeEmbeddings()
    verified_store = _FakeStore(
        [{
            "id": "verified-1",
            "score": 0.9,
            "payload": {"id": "vq_001", "question": "Revenue?", "content": "example"},
        }]
    )
    schema_store = _FakeStore(
        [{
            "id": "schema-1",
            "score": 0.8,
            "payload": {
                "type": "table",
                "table": "Sales.SalesOrderHeader",
                "qualified_name": "Sales.SalesOrderHeader",
                "content": "schema",
            },
        }]
    )
    monkeypatch.setattr(retriever, "get_embedding_client", lambda: embeddings)
    monkeypatch.setattr(
        retriever,
        "get_verified_queries_store",
        lambda: verified_store,
    )
    monkeypatch.setattr(
        retriever,
        "get_semantic_schema_store",
        lambda: schema_store,
    )

    verified, schema = asyncio.run(
        retriever.retrieve_text_to_sql_context(
            "Total revenue in 2013",
            verified_top_k=5,
            schema_top_k=8,
        )
    )

    assert embeddings.questions == ["Total revenue in 2013"]
    assert verified == verified_store.result
    assert schema == schema_store.result
    assert verified_store.searches == [([0.1, 0.2, 0.3], 5)]
    assert schema_store.searches == [([0.1, 0.2, 0.3], 8)]


def test_runtime_clients_are_cached(monkeypatch) -> None:
    created = {"embeddings": 0, "stores": 0}

    class FakeEmbeddingClient:
        def __init__(self) -> None:
            created["embeddings"] += 1

    class FakeQdrantStore:
        def __init__(self, _: str) -> None:
            created["stores"] += 1

    retriever.get_embedding_client.cache_clear()
    retriever.get_verified_queries_store.cache_clear()
    retriever.get_semantic_schema_store.cache_clear()
    monkeypatch.setattr(retriever, "OllamaEmbeddings", FakeEmbeddingClient)
    monkeypatch.setattr(retriever, "QdrantStore", FakeQdrantStore)

    try:
        assert retriever.get_embedding_client() is retriever.get_embedding_client()
        assert (
            retriever.get_verified_queries_store()
            is retriever.get_verified_queries_store()
        )
        assert (
            retriever.get_semantic_schema_store()
            is retriever.get_semantic_schema_store()
        )
        assert created == {"embeddings": 1, "stores": 2}
    finally:
        retriever.get_embedding_client.cache_clear()
        retriever.get_verified_queries_store.cache_clear()
        retriever.get_semantic_schema_store.cache_clear()
