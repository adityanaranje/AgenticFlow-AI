"""Tests for the retrieval service (Phase 4, §15)."""

from app.services import retrieval


def _fake_search(organization_id=None, query_vector=None, top_k=5, filters=None):
    # Assert the retrieval layer always passes an organization.
    assert organization_id, "retrieval must scope to an organization"
    return [
        {
            "score": 0.91,
            "id": "vec-1",
            "payload": {
                "organization_id": organization_id,
                "document_id": "doc-1",
                "document_chunk_id": "chunk-1",
                "filename": "policy.pdf",
                "page_number": 12,
                "chunk_index": 3,
                "content": "Some retrieved text.",
            },
        }
    ]


def test_retrieve_context_structured_results(monkeypatch):
    monkeypatch.setattr("app.services.embeddings.embed_query", lambda q: [0.1, 0.2, 0.3])
    monkeypatch.setattr("app.services.vector_store.search_vectors", _fake_search)

    results = retrieval.retrieve_context(
        organization_id="org-A", query="data policy", top_k=5
    )
    assert len(results) == 1
    row = results[0]
    assert row["document_id"] == "doc-1"
    assert row["chunk_id"] == "chunk-1"
    assert row["content"] == "Some retrieved text."
    assert row["score"] == 0.91
    assert row["metadata"]["filename"] == "policy.pdf"
    assert row["metadata"]["page_number"] == 12


def test_retrieve_context_passes_filters(monkeypatch):
    seen = {}

    def fake_search(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr("app.services.embeddings.embed_query", lambda q: [0.0])
    monkeypatch.setattr("app.services.vector_store.search_vectors", fake_search)

    retrieval.retrieve_context(
        organization_id="org-A",
        query="q",
        top_k=3,
        filters={"document_id": "doc-9"},
    )
    assert seen.get("organization_id") == "org-A"
    assert seen.get("filters") == {"document_id": "doc-9"}


def test_retrieve_context_empty_query(monkeypatch):
    monkeypatch.setattr("app.services.vector_store.search_vectors", _fake_search)
    assert retrieval.retrieve_context("org-A", "   ") == []
