"""Qdrant vector store operations (Phase 4, §10).

Responsibilities:
    - ensure the collection exists with a dimension matching the embedding
      model (``EMBEDDING_DIMENSIONS``), Cosine distance,
    - upsert chunk vectors with tenant-safe payloads,
    - delete all vectors for a document,
    - search with a mandatory ``organization_id == <org>`` filter.

Every stored point carries ``organization_id`` (plus document/chunk linkage)
so retrieval can NEVER run an unrestricted vector search. The Qdrant filter
is the first line of tenant isolation; the FastAPI layer also re-validates
membership before serving results.
"""

from __future__ import annotations

from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.qdrant import get_qdrant_client

logger = get_logger(__name__)

DISTANCE = qmodels.Distance.COSINE


def _client() -> QdrantClient:
    client = get_qdrant_client()
    if client is None:
        raise RuntimeError(
            "Qdrant is not configured; cannot perform vector operations."
        )
    return client


# Payload fields used in every tenant-scoped filter. Qdrant requires a
# payload index for filtered fields — strict clusters (e.g. Qdrant Cloud)
# REJECT unindexed filter deletes/searches with:
#   "Index required but not found for \"organization_id\" of one of the
#    following types: [keyword, uuid]"
# so the indexes are ensured alongside the collection.
_FILTER_INDEX_FIELDS: tuple[str, ...] = ("organization_id", "document_id")

_payload_indexes_ready = False


def _ensure_payload_indexes(client: QdrantClient) -> None:
    """Create payload indexes for the tenant-filter fields (idempotent)."""
    global _payload_indexes_ready
    if _payload_indexes_ready:
        return

    name = settings.qdrant_collection
    try:
        info = client.get_collection(name)
        existing = getattr(info, "payload_schema", None) or {}
    except Exception:
        existing = {}

    ok = True
    for field in _FILTER_INDEX_FIELDS:
        if field in existing:
            continue
        try:
            client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.UUID,
            )
            logger.info("Created Qdrant payload index %s.%s", name, field)
        except Exception:
            ok = False
            logger.warning(
                "Could not create payload index for %s.%s — strict Qdrant "
                "clusters reject filtered vector operations without it.",
                name,
                field,
                exc_info=True,
            )
    if ok:
        _payload_indexes_ready = True


def ensure_collection(client: Optional[QdrantClient] = None) -> None:
    """Create the collection if it does not exist (dimension = model),
    and ensure the payload indexes required for tenant-scoped filtering."""
    client = client or _client()
    name = settings.qdrant_collection
    collections = client.get_collections().collections
    if not any(c.name == name for c in collections):
        client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(
                size=settings.embedding_dimensions,
                distance=DISTANCE,
            ),
        )
        logger.info(
            "Created Qdrant collection %s (dims=%s)", name, settings.embedding_dimensions
        )

    _ensure_payload_indexes(client)


def upsert_chunk_vectors(
    points: list[dict[str, Any]],
    client: Optional[QdrantClient] = None,
) -> None:
    """Upsert vectors.

    ``points`` is a list of dicts with keys:
        id (str uuid), vector (list[float]), and payload fields below.
    """
    if not points:
        return
    client = client or _client()
    ensure_collection(client)
    payload = [
        qmodels.PointStruct(
            id=point["id"],
            vector=point["vector"],
            payload=point["payload"],
        )
        for point in points
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=payload)


def _document_filter(
    organization_id: str, document_id: Optional[str] = None
) -> qmodels.Filter:
    must: list[Any] = [
        qmodels.FieldCondition(
            key="organization_id", match=qmodels.MatchValue(value=organization_id)
        )
    ]
    if document_id:
        must.append(
            qmodels.FieldCondition(
                key="document_id", match=qmodels.MatchValue(value=document_id)
            )
        )
    return qmodels.Filter(must=must)


def delete_document_vectors(
    organization_id: str,
    document_id: str,
    client: Optional[QdrantClient] = None,
) -> None:
    """Remove every vector belonging to ``document_id`` within an org."""
    client = client or _client()
    try:
        client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=qmodels.FilterSelector(
                filter=_document_filter(organization_id, document_id)
            ),
        )
    except Exception:
        logger.exception(
            "Failed to delete Qdrant vectors for document %s", document_id
        )
        raise


def search_vectors(
    *,
    organization_id: str,
    query_vector: list[float],
    top_k: int = 5,
    filters: Optional[dict[str, Any]] = None,
    client: Optional[QdrantClient] = None,
) -> list[dict[str, Any]]:
    """Search vectors scoped to an organization.

    Never performs an unrestricted search: ``organization_id`` is always
    applied as a hard filter. Optional ``filters`` dict is AND-ed on top
    (e.g. ``{"document_id": "<uuid>"}``).
    """
    client = client or _client()
    ensure_collection(client)

    must: list[Any] = [
        qmodels.FieldCondition(
            key="organization_id", match=qmodels.MatchValue(value=organization_id)
        )
    ]
    for key, value in (filters or {}).items():
        if value is None:
            continue
        if isinstance(value, list):
            must.append(
                qmodels.FieldCondition(
                    key=key, match=qmodels.MatchAny(any=[str(v) for v in value])
                )
            )
        else:
            must.append(
                qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=str(value)))
            )

    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        query_filter=qmodels.Filter(must=must),
        limit=top_k,
        with_payload=True,
    )

    return [
        {
            "score": hit.score,
            "id": str(hit.id),
            "payload": dict(hit.payload or {}),
        }
        for hit in results
    ]
