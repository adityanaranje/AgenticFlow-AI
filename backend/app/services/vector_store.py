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


def _create_collection(client: QdrantClient, name: str) -> None:
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


def _collection_is_compatible(client: QdrantClient, name: str) -> bool:
    """Whether the existing collection matches this app's vector layout:
    a single UNNAMED dense vector of ``embedding_dimensions`` (Cosine),
    and no sparse-only layout.

    Returns True when the shape cannot be inspected (introspection failures
    must never trigger a destructive recreate)."""
    try:
        info = client.get_collection(name)
        params = getattr(getattr(info, "config", None), "params", None)
        vectors = getattr(params, "vectors", None)
    except Exception:
        logger.debug("Could not inspect collection %s config", name, exc_info=True)
        return True

    if vectors is None:
        # No dense vectors at all. A sparse-only collection (or one with an
        # empty vector map) is equally unusable — every unnamed dense
        # upsert/search 400s with "Not existing vector name error".
        # If we cannot see sparse vectors either, introspection is
        # incomplete; never recreate on incomplete information.
        return not bool(getattr(params, "sparse_vectors", None))
    if not isinstance(vectors, qmodels.VectorParams):
        return False  # named-vector layout (or empty) — our unnamed uploads would 400
    if vectors.size != settings.embedding_dimensions:
        return False
    if vectors.distance != DISTANCE:
        return False
    return True


def _recreate_incompatible_collection(client: QdrantClient) -> bool:
    """Drop and recreate the collection when its stored vector layout is
    incompatible with this app's unnamed-vector requests.

    Returns True when the collection was recreated (and the tenant-filter
    payload indexes were rebuilt); False when the collection looks
    compatible — meaning an observed vector error is NOT fixable by a
    recreate and must surface to the caller."""
    global _payload_indexes_ready

    name = settings.qdrant_collection
    if _collection_is_compatible(client, name):
        return False

    logger.warning(
        "Qdrant collection %s has an incompatible vector layout for this "
        "app (single unnamed vector, dims=%s, cosine) — dropping and "
        "recreating it. Re-process documents to repopulate vectors.",
        name,
        settings.embedding_dimensions,
    )
    client.delete_collection(name)
    _create_collection(client, name)
    _payload_indexes_ready = False  # indexes dropped with the collection
    _ensure_payload_indexes(client)
    return True


# Substrings identifying Qdrant HTTP 400s caused purely by the collection's
# vector layout rejecting our unnamed-vector requests (e.g. a collection
# created externally with named vectors):
#   "Wrong input: Not existing vector name error: "
_LAYOUT_ERROR_MARKERS: tuple[str, ...] = (
    "Not existing vector name error",
    "Vector dimension error",
)


def _is_vector_layout_error(exc: BaseException) -> bool:
    """Whether a Qdrant error indicates the collection's vector layout
    rejected this app's (unnamed, fixed-dimension) vector request.

    Detection is by response text so it works across client transports;
    the recreate itself only happens after re-inspecting the collection
    (see :func:`_recreate_incompatible_collection`)."""
    text = str(getattr(exc, "content", "") or "") or str(exc)
    return any(marker in text for marker in _LAYOUT_ERROR_MARKERS)


def ensure_collection(client: Optional[QdrantClient] = None) -> None:
    """Create the collection if it does not exist (dimension = model),
    and ensure the payload indexes required for tenant-scoped filtering.

    An existing collection with an INCOMPATIBLE vector layout (named
    vectors, sparse-only, wrong dimension or distance) is unusable by this
    app — every upsert/search fails ("Not existing vector name error") —
    so it is dropped and recreated with a loud warning."""
    global _payload_indexes_ready

    client = client or _client()
    name = settings.qdrant_collection
    collections = client.get_collections().collections
    exists = any(c.name == name for c in collections)

    if not exists:
        _create_collection(client, name)
    else:
        _recreate_incompatible_collection(client)

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
    try:
        client.upsert(collection_name=settings.qdrant_collection, points=payload)
        return
    except Exception as exc:
        if not _is_vector_layout_error(exc):
            raise
        # The collection was (re)created or mutated out-of-band with a
        # layout this app cannot write to. Verify + rebuild, then retry
        # exactly once; a second failure surfaces below.
        logger.warning(
            "Qdrant upsert rejected with a vector-layout error — attempting "
            "one self-heal recreate of collection %s (%s)",
            settings.qdrant_collection,
            exc,
        )
        if not _recreate_incompatible_collection(client):
            raise  # collection looks compatible; recreate cannot fix this
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


def _execute_search(
    client: QdrantClient,
    *,
    collection_name: str,
    query_vector: list[float],
    query_filter: qmodels.Filter,
    limit: int,
) -> list[Any]:
    """Run a dense vector search across qdrant-client versions.

    qdrant-client >= 1.19 REMOVED the deprecated ``search`` method (an
    ``AttributeError`` at call time on fresh installs); ``query_points``
    is its replacement since 1.10. Older clients only have ``search``.
    """
    if hasattr(client, "query_points"):
        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return list(response.points or [])
    return client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )


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

    try:
        results = _execute_search(
            client,
            collection_name=settings.qdrant_collection,
            query_vector=query_vector,
            query_filter=qmodels.Filter(must=must),
            limit=top_k,
        )
    except Exception as exc:
        if not _is_vector_layout_error(exc):
            raise
        logger.warning(
            "Qdrant search rejected with a vector-layout error — attempting "
            "one self-heal recreate of collection %s (%s)",
            settings.qdrant_collection,
            exc,
        )
        if not _recreate_incompatible_collection(client):
            raise
        results = _execute_search(
            client,
            collection_name=settings.qdrant_collection,
            query_vector=query_vector,
            query_filter=qmodels.Filter(must=must),
            limit=top_k,
        )

    return [
        {
            "score": hit.score,
            "id": str(hit.id),
            "payload": dict(hit.payload or {}),
        }
        for hit in results
    ]
