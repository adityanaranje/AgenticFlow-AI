"""Semantic retrieval over a tenant's knowledge base (Phase 4, §15)."""

from __future__ import annotations

from typing import Any, Optional

from app.services import embeddings
from app.services import vector_store


def retrieve_context(
    organization_id: str,
    query: str,
    top_k: int = 5,
    filters: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Return the top-``top_k`` chunks relevant to ``query`` in an org.

    The embedding model and Qdrant collection must be configured. Results
    are always scoped to ``organization_id`` (mandatory tenant filter).
    """
    if not query or not query.strip():
        return []

    query_vector = embeddings.embed_query(query.strip())

    hits = vector_store.search_vectors(
        organization_id=organization_id,
        query_vector=query_vector,
        top_k=max(1, int(top_k)),
        filters=filters,
    )

    results: list[dict[str, Any]] = []
    for hit in hits:
        payload = hit.get("payload") or {}
        results.append(
            {
                "document_id": payload.get("document_id"),
                "chunk_id": payload.get("document_chunk_id"),
                "vector_point_id": hit.get("id"),
                "content": payload.get("content"),
                "filename": payload.get("filename"),
                "page_number": payload.get("page_number"),
                "chunk_index": payload.get("chunk_index"),
                "score": hit.get("score"),
                "metadata": {
                    "filename": payload.get("filename"),
                    "page_number": payload.get("page_number"),
                    "chunk_index": payload.get("chunk_index"),
                    "organization_id": payload.get("organization_id"),
                },
            }
        )
    return results
