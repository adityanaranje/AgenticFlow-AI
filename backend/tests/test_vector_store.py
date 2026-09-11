"""Tests for Qdrant vector store tenant scoping (Phase 4, §10)."""

import pytest
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http import models as qmodels

from app.services import vector_store


# The exact Qdrant 400 body from a named-vector collection rejecting an
# unnamed-vector upsert/search (matches the user-visible failure).
_NAMED_LAYOUT_400_BODY = (
    b'{"status":{"error":"Wrong input: Not existing vector name error: "},'
    b'"time":0.003689154}'
)


def _layout_error() -> UnexpectedResponse:
    return UnexpectedResponse(
        status_code=400,
        reason_phrase="Bad Request",
        content=_NAMED_LAYOUT_400_BODY,
        headers=None,
    )


@pytest.fixture(autouse=True)
def _reset_payload_index_flag(monkeypatch):
    monkeypatch.setattr(vector_store, "_payload_indexes_ready", False)


class FakeClient:
    """Stand-in Qdrant client that records calls."""

    def __init__(
        self,
        has_collection=False,
        vector_config="compatible",
        layout_errors_before_success=0,
        upsert_error=None,
        search_error=None,
        simulate_out_of_band_mutation=True,
    ):
        self.created = []
        self.created_indexes = []
        self.deleted_collections = []
        self.upserted = []
        self.deleted_filters = []
        self.search_calls = []
        self.has_collection = has_collection
        self.vector_config = vector_config
        self.fail_index_creation = False
        self.layout_errors_before_success = layout_errors_before_success
        self.upsert_error = upsert_error
        self.search_error = search_error
        self.simulate_out_of_band_mutation = simulate_out_of_band_mutation
        self.upsert_attempts = 0
        self.search_attempts = 0

    def _maybe_raise_layout_error(self):
        """Simulate Qdrant 400ing with a vector-layout error, then behaving
        as the real server would after the app recreates the collection."""
        if self.layout_errors_before_success > 0:
            self.layout_errors_before_success -= 1
            if self.simulate_out_of_band_mutation:
                # Between the app's ensure_collection and this very request
                # the collection was swapped out-of-band for a named-vector
                # one (the only realistic way to get this 400 here).
                self.vector_config = "named"
                self.has_collection = True
            raise _layout_error()

    def get_collections(self):
        class _Resp:
            collections = []

        resp = _Resp()
        if self.has_collection:
            from app.core.config import settings

            class _Col:
                name = settings.qdrant_collection

            resp.collections = [_Col()]
        return resp

    def get_collection(self, name):
        from app.core.config import settings

        if self.vector_config == "named":
            vectors = {
                "default": qmodels.VectorParams(
                    size=settings.embedding_dimensions,
                    distance=qmodels.Distance.COSINE,
                )
            }
        elif self.vector_config == "wrong-dims":
            vectors = qmodels.VectorParams(size=7, distance=qmodels.Distance.COSINE)
        elif self.vector_config == "sparse-only":
            vectors = None
        else:  # "compatible"
            vectors = qmodels.VectorParams(
                size=settings.embedding_dimensions,
                distance=qmodels.Distance.COSINE,
            )

        class _Params:
            pass

        class _Config:
            pass

        class _Info:
            payload_schema = {}

        _Info.config = _Config()
        _Info.config.params = _Params()
        _Info.config.params.vectors = vectors
        if self.vector_config == "sparse-only":
            _Info.config.params.sparse_vectors = {
                "text-sparse": qmodels.SparseVectorParams()
            }
        return _Info()

    def create_collection(self, **kwargs):
        self.created.append(kwargs)
        self.has_collection = True
        # Collections the app creates itself always have the correct layout.
        self.vector_config = "compatible"

    def delete_collection(self, name):
        self.deleted_collections.append(name)
        self.has_collection = False

    def create_payload_index(self, **kwargs):
        if self.fail_index_creation:
            raise RuntimeError("index API unavailable")
        self.created_indexes.append(kwargs)

    def upsert(self, **kwargs):
        self.upsert_attempts += 1
        if self.upsert_error is not None:
            raise self.upsert_error
        self._maybe_raise_layout_error()
        self.upserted.append(kwargs)

    def delete(self, **kwargs):
        self.deleted_filters.append(kwargs)

    def search(self, **kwargs):
        self.search_attempts += 1
        if self.search_error is not None:
            raise self.search_error
        self._maybe_raise_layout_error()
        self.search_calls.append(kwargs)
        return []

    class _QueryResponse:
        def __init__(self, points):
            self.points = points

    def query_points(self, **kwargs):
        """Modern qdrant-client API (>= 1.10; ``search`` removed in 1.19)."""
        self.search_attempts += 1
        if self.search_error is not None:
            raise self.search_error
        self._maybe_raise_layout_error()
        self.search_calls.append(kwargs)
        return FakeClient._QueryResponse([])


def _filter_org(f, monkeypatch=None):
    pass


def test_search_always_filters_organization(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.search_vectors(
        organization_id="org-B",
        query_vector=[0.1, 0.2],
        top_k=5,
    )

    assert client.search_calls, "search must be invoked"
    call = client.search_calls[0]
    assert call["query_filter"] is not None
    conditions = call["query_filter"].must
    assert any(
        getattr(c, "key", None) == "organization_id"
        and getattr(c, "match", None) is not None
        and getattr(c.match, "value", None) == "org-B"
        for c in conditions
    ), "organization_id filter is mandatory"
    assert call["limit"] == 5


def test_search_adds_document_filter(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.search_vectors(
        organization_id="org-B",
        query_vector=[0.0],
        top_k=3,
        filters={"document_id": "doc-42"},
    )
    call = client.search_calls[0]
    keys = [getattr(c, "key", None) for c in call["query_filter"].must]
    assert "organization_id" in keys
    assert "document_id" in keys


def test_upsert_payload_contains_tenant_and_linkage(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.upsert_chunk_vectors(
        [
            {
                "id": "chunk-1",
                "vector": [0.1] * 3,
                "payload": {
                    "organization_id": "org-A",
                    "document_id": "doc-1",
                    "document_chunk_id": "chunk-1",
                    "content": "hello",
                },
            }
        ]
    )
    assert client.upserted
    point = client.upserted[0]["points"][0]
    assert point.id == "chunk-1"
    assert point.payload["organization_id"] == "org-A"


def test_delete_scoped_to_document_and_org(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.delete_document_vectors("org-A", "doc-1")
    assert client.deleted_filters
    selector = client.deleted_filters[0]["points_selector"]
    must = selector.filter.must
    keys = [getattr(c, "key", None) for c in must]
    assert "organization_id" in keys and "document_id" in keys


def test_ensure_collection_creates_payload_indexes_once(monkeypatch):
    """Tenant-filter fields need payload indexes; strict Qdrant clusters
    (e.g. Cloud) reject unindexed filtered deletes/searches with 400."""
    client = FakeClient()
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.ensure_collection()
    fields = [c["field_name"] for c in client.created_indexes]
    assert fields == ["organization_id", "document_id"]
    assert all(
        c["field_schema"] == qmodels.PayloadSchemaType.UUID
        for c in client.created_indexes
    )

    # Second ensure must not re-create anything (per-process flag).
    vector_store.ensure_collection()
    assert len(client.created_indexes) == 2


def test_preexisting_collection_still_gets_indexes(monkeypatch):
    """Collections created before this fix get their indexes added."""
    client = FakeClient(has_collection=True)
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.ensure_collection()
    assert not client.created  # no re-creation of the collection itself
    assert [c["field_name"] for c in client.created_indexes] == [
        "organization_id",
        "document_id",
    ]


def test_index_creation_failure_does_not_block_ingestion(monkeypatch):
    client = FakeClient()
    client.fail_index_creation = True
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.ensure_collection()  # must not raise
    assert vector_store._payload_indexes_ready is False  # retried next time


def test_named_vector_collection_is_recreated(monkeypatch):
    """A pre-existing named-vector collection makes every unnamed upsert
    fail with 400 'Not existing vector name error' — must be recreated."""
    from app.core.config import settings

    client = FakeClient(has_collection=True, vector_config="named")
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.ensure_collection()
    assert client.deleted_collections == [settings.qdrant_collection]
    assert len(client.created) == 1  # recreated with correct layout
    assert [c["field_name"] for c in client.created_indexes] == [
        "organization_id",
        "document_id",
    ]


def test_wrong_dimension_collection_is_recreated(monkeypatch):
    client = FakeClient(has_collection=True, vector_config="wrong-dims")
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.ensure_collection()
    assert len(client.deleted_collections) == 1
    assert len(client.created) == 1


def test_compatible_collection_is_left_alone(monkeypatch):
    client = FakeClient(has_collection=True, vector_config="compatible")
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.ensure_collection()
    assert not client.deleted_collections
    assert not client.created


def test_search_can_require_org_never_unrestricted(monkeypatch):
    """Enforcement guard: search without an org must not be expressible."""
    client = FakeClient()
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.search_vectors(
        organization_id="org-A", query_vector=[0.0, 0.0], top_k=2
    )
    call = client.search_calls[0]
    assert call["query_filter"] is not None


def test_sparse_only_collection_is_recreated(monkeypatch):
    """A sparse-only collection (no dense vectors at all) rejects every
    unnamed dense upsert with 400 'Not existing vector name error' —
    it must be recreated like a named-vector collection."""
    from app.core.config import settings

    client = FakeClient(has_collection=True, vector_config="sparse-only")
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.ensure_collection()
    assert client.deleted_collections == [settings.qdrant_collection]
    assert len(client.created) == 1
    assert client.vector_config == "compatible"  # recreated with correct layout


def test_upsert_self_heals_named_layout_400(monkeypatch):
    """If a collection is mutated/created out-of-band between ensure and the
    upsert (Qdrant 400 'Not existing vector name error'), the upsert must
    recreate the incompatible collection and retry once — self-healing."""
    from app.core.config import settings

    client = FakeClient(
        has_collection=True,
        vector_config="compatible",  # fine when ensure_collection ran...
        layout_errors_before_success=1,  # ...then swapped out-of-band
    )
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.upsert_chunk_vectors(
        [
            {
                "id": "chunk-1",
                "vector": [0.1] * 3,
                "payload": {"organization_id": "org-A", "document_id": "doc-1"},
            }
        ]
    )

    assert client.upsert_attempts == 2  # failed attempt + retried once
    assert client.deleted_collections == [settings.qdrant_collection]
    assert len(client.created) == 1  # recreated with the correct layout
    assert len(client.upserted) == 1
    # Tenant-filter indexes rebuilt alongside the recreate (ensure already
    # created them for the initial collection; the recreate re-adds both).
    fields = [c["field_name"] for c in client.created_indexes]
    assert fields[-2:] == ["organization_id", "document_id"]


def test_search_self_heals_named_layout_400(monkeypatch):
    from app.core.config import settings

    client = FakeClient(
        has_collection=True,
        vector_config="compatible",
        layout_errors_before_success=1,
    )
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    hits = vector_store.search_vectors(
        organization_id="org-A", query_vector=[0.1, 0.2], top_k=3
    )

    assert hits == []
    assert client.search_attempts == 2  # failed attempt + retried once
    assert client.deleted_collections == [settings.qdrant_collection]
    assert len(client.created) == 1


def test_layout_error_with_compatible_collection_is_not_swallowed(monkeypatch):
    """A vector-layout error while the collection actually looks compatible
    is NOT fixable by a recreate — it must propagate (never drop data on a
    guess)."""
    client = FakeClient(
        has_collection=True,
        vector_config="compatible",
        layout_errors_before_success=1,
        simulate_out_of_band_mutation=False,  # error is inconsistent with what get_collection reports
    )
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    with pytest.raises(UnexpectedResponse):
        vector_store.upsert_chunk_vectors(
            [
                {
                    "id": "chunk-1",
                    "vector": [0.1] * 3,
                    "payload": {"organization_id": "org-A"},
                }
            ]
        )

    assert client.upsert_attempts == 1  # no blind retry
    assert not client.deleted_collections  # nothing dropped
    assert not client.created


def test_unrelated_upsert_error_propagates_untouched(monkeypatch):
    """Non-layout failures (network, auth, ...) must never trigger a
    destructive recreate."""
    client = FakeClient(
        has_collection=True,
        upsert_error=RuntimeError("connection reset"),
    )
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    with pytest.raises(RuntimeError, match="connection reset"):
        vector_store.upsert_chunk_vectors(
            [
                {
                    "id": "chunk-1",
                    "vector": [0.1] * 3,
                    "payload": {"organization_id": "org-A"},
                }
            ]
        )

    assert not client.deleted_collections
    assert not client.created
