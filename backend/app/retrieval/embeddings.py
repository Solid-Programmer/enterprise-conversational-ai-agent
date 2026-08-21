"""Ollama embedding client using the nomic retrieval prefixes."""

from typing import List, Sequence

import httpx

from app.core.config import settings


DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


class OllamaEmbeddings:
    """Embed documents and queries through Ollama's `/api/embed` endpoint."""

    def __init__(self, base_url: str = settings.OLLAMA_BASE_URL, model: str = settings.OLLAMA_EMBED_MODEL) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        return self._embed([DOCUMENT_PREFIX + text for text in texts])

    def embed_query(self, question: str) -> List[float]:
        return self._embed([QUERY_PREFIX + question])[0]

    def _embed(self, inputs: Sequence[str]) -> List[List[float]]:
        if not inputs:
            return []
        response = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": list(inputs)},
            timeout=60.0,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings")
        if not embeddings or len(embeddings) != len(inputs):
            raise RuntimeError("Ollama returned an invalid embedding response.")
        return embeddings
