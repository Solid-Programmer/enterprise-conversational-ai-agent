"""Small Qdrant wrapper shared by the two independent retrieval collections."""

from typing import Any, Dict, Iterable, List, Sequence

from qdrant_client import QdrantClient, models

from app.core.config import settings


VERIFIED_QUERIES_COLLECTION = "verified_queries"
SEMANTIC_SCHEMA_COLLECTION = "semantic_schema"


class QdrantStore:
    """Creates, upserts, and searches a single named Qdrant collection."""

    def __init__(self, collection_name: str, url: str = settings.QDRANT_URL) -> None:
        self.collection_name = collection_name
        self.client = QdrantClient(url=url)

    def ensure_collection(self, vector_size: int, recreate: bool = False) -> None:
        if recreate and self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
            )

    def upsert(self, ids: Sequence[str], vectors: Sequence[Sequence[float]], payloads: Sequence[Dict[str, Any]]) -> None:
        self.client.upsert(
            collection_name=self.collection_name,
            points=[models.PointStruct(id=point_id, vector=vector, payload=payload)
                    for point_id, vector, payload in zip(ids, vectors, payloads)],
            wait=True,
        )

    def search(self, vector: Sequence[float], limit: int) -> List[Dict[str, Any]]:
        results = self.client.query_points(
            collection_name=self.collection_name, query=list(vector), limit=limit, with_payload=True
        ).points
        return [{"id": str(result.id), "score": result.score, "payload": result.payload} for result in results]

    def count(self) -> int:
        return self.client.count(collection_name=self.collection_name, exact=True).count
