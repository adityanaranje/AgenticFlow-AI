"""Reprocess endpoint tests (recovering FAILED documents).

A transient backend failure (e.g. a misconfigured vector store) marks
documents failed even though the stored file is fine — reprocessing must
reset the record and re-run the standard ingestion pipeline.
"""

import pytest
from fastapi import HTTPException

from app.api import documents as documents_api


class FakeRepo:
    def __init__(self, record):
        self.record = dict(record) if record else None
        self.updates = []

    def get_by_id(self, document_id, organization_id):
        if (
            self.record is not None
            and self.record.get("id") == document_id
            and self.record.get("organization_id") == organization_id
        ):
            return dict(self.record)
        return None

    def update(self, document_id, organization_id, fields):
        self.updates.append((document_id, organization_id, dict(fields)))
        self.record.update(fields)
        return dict(self.record)


@pytest.fixture
def failed_doc():
    return {
        "id": "doc-1",
        "organization_id": "org-A",
        "filename": "report.txt",
        "status": "failed",
        "processing_error": "Qdrant 400",
    }


def test_reprocess_resets_status_and_enqueues(monkeypatch, failed_doc):
    repo = FakeRepo(failed_doc)
    monkeypatch.setattr(documents_api, "DocumentRepository", lambda: repo)
    enqueued = []
    monkeypatch.setattr(
        documents_api.job_queue, "enqueue_document", lambda doc_id: enqueued.append(doc_id) or True
    )

    result = documents_api.reprocess_document(
        organization_id="org-A", document_id="doc-1", membership=None
    )

    assert enqueued == ["doc-1"]
    # Status reset to pending with the error cleared, BEFORE enqueueing.
    assert repo.updates[0][2] == {"status": "pending", "processing_error": None}
    assert result["queued"] is True
    assert result["document"]["status"] == "pending"


def test_reprocess_runs_inline_when_redis_absent(monkeypatch, failed_doc):
    repo = FakeRepo(failed_doc)
    monkeypatch.setattr(documents_api, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(documents_api.job_queue, "enqueue_document", lambda _: False)
    processed = []
    import app.workers.document_worker as worker

    monkeypatch.setattr(
        worker, "process_document", lambda doc_id: processed.append(doc_id)
    )

    result = documents_api.reprocess_document(
        organization_id="org-A", document_id="doc-1", membership=None
    )

    assert processed == ["doc-1"]
    assert result["queued"] is False


def test_reprocess_rejects_in_flight_document(monkeypatch, failed_doc):
    failed_doc["status"] = "processing"
    repo = FakeRepo(failed_doc)
    monkeypatch.setattr(documents_api, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(documents_api.job_queue, "enqueue_document", lambda _: True)

    with pytest.raises(HTTPException) as exc_info:
        documents_api.reprocess_document(
            organization_id="org-A", document_id="doc-1", membership=None
        )
    assert exc_info.value.status_code == 409
    assert repo.updates == []  # nothing was reset


def test_reprocess_allows_completed_document(monkeypatch, failed_doc):
    """Completed documents can be reprocessed to rebuild derived data /
    metadata (e.g. legacy rows with a null page count)."""
    failed_doc["status"] = "completed"
    failed_doc["page_count"] = None
    repo = FakeRepo(failed_doc)
    monkeypatch.setattr(documents_api, "DocumentRepository", lambda: repo)
    enqueued = []
    monkeypatch.setattr(
        documents_api.job_queue, "enqueue_document", lambda doc_id: enqueued.append(doc_id) or True
    )

    result = documents_api.reprocess_document(
        organization_id="org-A", document_id="doc-1", membership=None
    )

    assert enqueued == ["doc-1"]
    assert result["document"]["status"] == "pending"


def test_reprocess_missing_document_is_404(monkeypatch):
    repo = FakeRepo(None)
    monkeypatch.setattr(documents_api, "DocumentRepository", lambda: repo)

    with pytest.raises(HTTPException) as exc_info:
        documents_api.reprocess_document(
            organization_id="org-A", document_id="doc-404", membership=None
        )
    assert exc_info.value.status_code == 404


def test_reprocess_route_is_registered():
    from app.main import app

    paths = app.openapi()["paths"]
    assert (
        "/api/v1/organizations/{organization_id}/documents/{document_id}/reprocess"
        in paths
    )
