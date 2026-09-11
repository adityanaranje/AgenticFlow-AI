"""Tests for Qdrant vector store tenant scoping (Phase 4, §10)."""

import pytest
from qdrant_client.http import models as qmodels

from app.services import vector_store


@pytest.fixture(autouse=True)
def _reset_payload_index_flag(monkeypatch):
    monkeypatch.setattr(vector_store, "_payload_indexes_ready", False)


class FakeClient:
    """Stand-in Qdrant client that records calls."""

    def __init__(self, has_collection=False, vector_config="compatible"):
        self.created = []
        self.created_indexes = []
        self.deleted_collections = []
        self.upserted = []
        self.deleted_filters = []
        self.search_calls = []
        self.has_collection = has_collection
        self.vector_config = vector_config
        self.fail_index_creation = False

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
        return _Info()

    def create_collection(self, **kwargs):
        self.created.append(kwargs)
        self.has_collection = True

    def delete_collection(self, name):
        self.deleted_collections.append(name)
        self.has_collection = False

    def create_payload_index(self, **kwargs):
        if self.fail_index_creation:
            raise RuntimeError("index API unavailable")
        self.created_indexes.append(kwargs)

    def upsert(self, **kwargs):
        self.upserted.append(kwargs)

    def delete(self, **kwargs):
        self.deleted_filters.append(kwargs)

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return []


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
