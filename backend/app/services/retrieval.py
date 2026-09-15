"""Semantic retrieval over a tenant's knowledge base (Phase 4, §15).

Retrieval is one embedding call plus one vector search. A research run issues
several queries at once (the question plus its planner sub-questions), so
:func:`retrieve_context_many` embeds every query in a single provider request
and runs the vector searches concurrently instead of paying that round trip
once per query.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services import embeddings, vector_store

logger = get_logger(__name__)


def _shape_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise raw vector-store hits into retrieval results."""
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


def _search_one(
    organization_id: str,
    query_vector: list[float],
    top_k: int,
    filters: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    hits = vector_store.search_vectors(
        organization_id=organization_id,
        query_vector=query_vector,
        top_k=top_k,
        filters=filters,
    )
    return _shape_hits(hits)


def retrieve_context(
    organization_id: str,
    query: str,
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return the top-``top_k`` chunks relevant to ``query`` in an org.

    The embedding model and Qdrant collection must be configured. Results
    are always scoped to ``organization_id`` (mandatory tenant filter).
    """
    if not query or not query.strip():
        return []

    query_vector = embeddings.embed_query(query.strip())
    return _search_one(organization_id, query_vector, max(1, int(top_k)), filters)


def retrieve_context_many(
    organization_id: str,
    queries: list[str],
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
    *,
    concurrency: int | None = None,
) -> list[list[dict[str, Any]]]:
    """Retrieve for several queries at once, preserving query order.

    All query texts go into **one** embeddings request (the provider takes a
    batch of inputs), and the vector searches then run concurrently: the
    result is one round trip plus the slowest search instead of
    ``len(queries)`` sequential round trips. Blank queries return ``[]``
    without any provider call.
    """
    texts = [query or "" for query in queries]
    results: list[list[dict[str, Any]]] = [[] for _ in texts]
    active = [(index, text.strip()) for index, text in enumerate(texts) if text.strip()]
    if not active:
        return results

    vectors = embeddings.embed_texts([text for _, text in active])
    if len(vectors) != len(active):
        raise RuntimeError(
            f"Embedding count mismatch: {len(vectors)} vectors for {len(active)} queries."
        )

    workers = max(1, int(concurrency or settings.retrieval_concurrency))
    limit = max(1, int(top_k))
    if len(active) == 1:
        index, _ = active[0]
        results[index] = _search_one(organization_id, vectors[0], limit, filters)
        return results

    # A shared client is used by every thread (the Qdrant client is
    # thread-safe and pooling a new one per search would redo the handshake).
    with ThreadPoolExecutor(
        max_workers=min(workers, len(active)), thread_name_prefix="retrieve"
    ) as pool:
        futures = {
            pool.submit(_search_one, organization_id, vector, limit, filters): index
            for (index, _), vector in zip(active, vectors)
        }
        for future, index in futures.items():
            results[index] = future.result()

    return results
