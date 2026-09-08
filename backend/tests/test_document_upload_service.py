"""Tests for the upload orchestration service (Phase 4, §3/§4/§5)."""

import uuid

from app.services import document_service


class FakeRepo:
    def __init__(self):
        self.created = []
        self.updated = []
        self.records = {}

    def create(self, data):
        row = dict(data)
        if "id" not in row or not row["id"]:
            row["id"] = str(uuid.uuid4())
        self.records[row["id"]] = row
        self.created.append(row)
        return row

    def get_by_id(self, document_id, organization_id):
        return self.records.get(document_id)

    def update(self, document_id, organization_id, fields):
        if document_id in self.records:
            self.records[document_id].update(fields)
        self.updated.append((document_id, fields))


def test_upload_creates_pending_then_stores_and_queues(monkeypatch):
    repo = FakeRepo()
    uploaded = []

    def fake_upload(organization_id, document_id, filename, data, content_type="x"):
        uploaded.append((organization_id, document_id, filename, content_type))
        return f"organizations/{organization_id}/documents/{document_id}/{filename}"

    def fake_enqueue(document_id):
        return True  # queued successfully -> no inline processing

    monkeypatch.setattr(document_service, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(document_service.document_storage, "upload_document", fake_upload)
    monkeypatch.setattr(document_service.job_queue, "enqueue_document", fake_enqueue)

    result = document_service.create_and_start_processing(
        user_id="user-1",
        organization_id="org-A",
        filename="notes.txt",
        content_type="text/plain",
        data=b"Hello world content.",
    )

    assert result is not None
    assert result["status"] == "pending"
    assert result["organization_id"] == "org-A"
    assert result["uploaded_by"] == "user-1"
    assert result["checksum"]  # stored for duplicate detection
    assert len(uploaded) == 1
    assert uploaded[0][1] == result["id"]
    # never trusts a client path; storage path is server-derived and scoped
    assert result["storage_path"].startswith("organizations/org-A/documents/")
    assert result["file_type"] == "txt"


def test_upload_rejects_unsupported(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(document_service, "DocumentRepository", lambda: repo)
    try:
        document_service.create_and_start_processing(
            user_id="u",
            organization_id="o",
            filename="evil.mp3",
            content_type="audio/mpeg",
            data=b"data",
        )
        raise AssertionError("expected rejection")
    except Exception as exc:
        assert type(exc).__name__ == "ValidationError"
        assert not repo.created
