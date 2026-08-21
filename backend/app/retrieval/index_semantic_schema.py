"""Create contextual semantic-schema documents and index them in Qdrant."""

import argparse
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

from app.retrieval.embeddings import OllamaEmbeddings
from app.retrieval.qdrant_store import QdrantStore, SEMANTIC_SCHEMA_COLLECTION


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sales" / "schema" / "sales_schema.json"
BUSINESS_RULES_PATH = Path(__file__).resolve().parent.parent / "sales" / "schema" / "sales_business_rules.json"
BATCH_SIZE = 32


def _table_document(table: Dict[str, Any]) -> Dict[str, Any]:
    columns = table.get("columns", [])
    column_lines = [
        f"{column.get('qualified_name', column['name'])} - {column.get('description') or column.get('data_type', '')}"
        for column in columns
    ]
    content = "\n".join([
        table["qualified_name"],
        f"Business meaning: {table.get('business_definition') or table.get('description') or ''}",
        f"Grain: {table.get('grain', '')}",
        f"Primary key: {', '.join(table.get('primary_key', []))}",
        "Important columns:",
        *column_lines,
    ])
    return {"type": "table", "table": table["qualified_name"], "qualified_name": table["qualified_name"], "content": content,
            "grain": table.get("grain"), "business_definition": table.get("business_definition"), "primary_key": table.get("primary_key", []),
            "columns": [column.get("qualified_name", column["name"]) for column in columns]}


def build_schema_chunks() -> List[Dict[str, Any]]:
    """Turn authoritative schema and business-rule JSON into contextual retrieval documents."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    rules = json.loads(BUSINESS_RULES_PATH.read_text(encoding="utf-8"))
    chunks = [_table_document(table) for table in schema.get("tables", [])]
    chunks.append({"type": "business_rule", "table": None, "qualified_name": "Sales.schema_overview",
                   "content": f"Sales schema overview: {schema.get('business_definition', '')}"})
    for relationship in schema.get("relationships", []):
        content = "\n".join([
            f"Relationship: {relationship.get('constraint_name', '')}",
            relationship.get("join_condition", ""),
            f"Cardinality: {relationship.get('cardinality', '')}",
        ])
        chunks.append({"type": "relationship", "table": relationship.get("from_qualified_table"),
                       "qualified_name": relationship.get("constraint_name"), "content": content, **relationship})
    for metric in schema.get("metrics", []):
        content = "\n".join([f"Metric: {metric.get('name', '')}", f"Meaning: {metric.get('description', '')}",
                             f"Expression: {metric.get('expression', '')}", f"Source: {metric.get('source_column', '')}"])
        chunks.append({"type": "metric", "table": metric.get("target_table"), "qualified_name": metric.get("qualified_name"),
                       "content": content, **metric})
    global_rules = rules.get("global_anti_hallucination_rules", [])
    if global_rules:
        chunks.append({"type": "business_rule", "table": None, "qualified_name": "Sales.global_rules",
                       "content": "Global Sales business rules:\n" + "\n".join(f"- {rule}" for rule in global_rules),
                       "rules": global_rules})
    for table_name, table_rules in rules.get("table_business_rules", {}).items():
        chunks.append({"type": "business_rule", "table": table_name, "qualified_name": f"{table_name}.business_rules",
                       "content": f"Business rules for {table_name}:\n" + json.dumps(table_rules, ensure_ascii=False, indent=2),
                       "rules": table_rules})
    return chunks


def index_semantic_schema(recreate: bool = False) -> int:
    """Create or update the semantic-schema collection and return its vector count."""
    chunks = build_schema_chunks()
    embedding_client = OllamaEmbeddings()
    store = QdrantStore(SEMANTIC_SCHEMA_COLLECTION)
    first_vector = embedding_client.embed_documents([chunks[0]["content"]])[0]
    store.ensure_collection(vector_size=len(first_vector), recreate=recreate)
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        batch_texts = [chunk["content"] for chunk in batch]
        vectors = ([first_vector] + embedding_client.embed_documents(batch_texts[1:])
                   if start == 0 else embedding_client.embed_documents(batch_texts))
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"semantic-schema:{chunk['type']}:{chunk.get('qualified_name')}")) for chunk in batch]
        store.upsert(ids, vectors, batch)
    count = store.count()
    print(f"Semantic schema chunks indexed: {count}")
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index Sales semantic schema documents in Qdrant.")
    parser.add_argument("--recreate", action="store_true", help="Delete and rebuild the collection first.")
    args = parser.parse_args()
    index_semantic_schema(recreate=args.recreate)
