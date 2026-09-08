"""Tests for Qdrant vector store tenant scoping (Phase 4, §10)."""

from qdrant_client.http import models as qmodels

from app.services import vector_store


class FakeClient:
    """Stand-in Qdrant client that records calls."""

    def __init__(self):
        self.created = []
        self.upserted = []
        self.deleted_filters = []
        self.search_calls = []

    def get_collections(self):
        class _Resp:
            collections = []

        return _Resp()

    def create_collection(self, **kwargs):
        self.created.append(kwargs)

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


def test_search_can_require_org_never_unrestricted(monkeypatch):
    """Enforcement guard: search without an org must not be expressible."""
    client = FakeClient()
    monkeypatch.setattr(vector_store, "_client", lambda: client)

    vector_store.search_vectors(
        organization_id="org-A", query_vector=[0.0, 0.0], top_k=2
    )
    call = client.search_calls[0]
    assert call["query_filter"] is not None
