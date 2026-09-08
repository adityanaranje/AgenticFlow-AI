"""OpenAI embedding generation (Phase 4, §9).

The embedding model is fully configurable via ``OPENAI_EMBEDDING_MODEL``;
the Qdrant collection dimension must match that model (``EMBEDDING_DIMENSIONS``)
— see :mod:`app.services.vector_store`. Nothing here hard-codes a dimension;
callers use :func:`settings.embedding_dimensions` to configure Qdrant.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.core.exceptions import ConfigurationError
from app.llm.client import get_openai_client


def _client():
    client = get_openai_client()
    if client is None:
        raise ConfigurationError(
            "OpenAI is not configured; cannot generate embeddings."
        )
    return client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts (batched by the API) and return them in order."""
    if not texts:
        return []
    cleaned = [text[:8000] for text in texts]
    client = _client()
    response = client.embeddings.create(
        model=settings.openai_embedding_model,
        input=cleaned,
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    return [list(item.embedding) for item in ordered]


def embed_query(query: str) -> list[float]:
    """Embed a single query string (used for retrieval)."""
    vectors = embed_texts([query])
    return vectors[0]


def embedding_dimension() -> int:
    """The configured vector dimension for the chosen embedding model."""
    return settings.embedding_dimensions
