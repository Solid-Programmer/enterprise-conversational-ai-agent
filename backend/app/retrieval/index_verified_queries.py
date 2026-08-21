"""Index the validated natural-language-to-SQL examples in Qdrant."""

import argparse
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

from app.retrieval.embeddings import OllamaEmbeddings
from app.retrieval.qdrant_store import QdrantStore, VERIFIED_QUERIES_COLLECTION


VERIFIED_QUERIES_PATH = Path(__file__).resolve().parent.parent / "sales" / "schema" / "verified_queries.json"
BATCH_SIZE = 32


def _intent_text(query: Dict[str, Any]) -> str:
    """Build an intent-led embedding document without making SQL the primary signal."""
    parts = [f"Question: {query.get('question', '')}"]
    for field, label in (("concepts", "Concepts"), ("tables", "Tables"), ("columns", "Columns"), ("difficulty", "Difficulty"), ("category", "Category")):
        value = query.get(field)
        if value:
            parts.append(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
    return "\n".join(parts)


def index_verified_queries(recreate: bool = False) -> int:
    """Create or update the verified-query collection and return its vector count."""
    queries: List[Dict[str, Any]] = json.loads(VERIFIED_QUERIES_PATH.read_text(encoding="utf-8"))
    embedding_client = OllamaEmbeddings()
    store = QdrantStore(VERIFIED_QUERIES_COLLECTION)
    texts = [_intent_text(query) for query in queries]
    first_vector = embedding_client.embed_documents(texts[:1])[0]
    store.ensure_collection(vector_size=len(first_vector), recreate=recreate)

    for start in range(0, len(queries), BATCH_SIZE):
        batch = queries[start:start + BATCH_SIZE]
        batch_texts = texts[start:start + BATCH_SIZE]
        vectors = ([first_vector] + embedding_client.embed_documents(batch_texts[1:])
                   if start == 0 else embedding_client.embed_documents(batch_texts))
        payloads = [{**query, "category": query.get("category", "verified_query"), "content": text}
                    for query, text in zip(batch, batch_texts)]
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"verified-query:{query.get('id', index)}"))
               for index, query in enumerate(batch, start=start)]
        store.upsert(ids, vectors, payloads)

    count = store.count()
    print(f"Verified queries indexed: {count}")
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index verified Sales NL-to-SQL examples in Qdrant.")
    parser.add_argument("--recreate", action="store_true", help="Delete and rebuild the collection first.")
    args = parser.parse_args()
    index_verified_queries(recreate=args.recreate)
