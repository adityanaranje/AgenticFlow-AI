"""Tests for the upload orchestration service (Phase 4, §3/§4/§5)."""

import uuid

from app.core.exceptions import ConflictError
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

    def get_by_checksum(self, organization_id, checksum):
        for row in self.records.values():
            if row.get("organization_id") == organization_id and row.get("checksum") == checksum:
                return row
        return None

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


def test_upload_rejects_duplicate_checksum(monkeypatch):
    """Re-uploading identical content to the same org is a friendly 409,
    not an opaque 500 from the unique index."""
    repo = FakeRepo()

    def fake_upload(organization_id, document_id, filename, data, content_type="x"):
        return f"organizations/{organization_id}/documents/{document_id}/{filename}"

    monkeypatch.setattr(document_service, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(document_service.document_storage, "upload_document", fake_upload)
    monkeypatch.setattr(
        document_service.job_queue, "enqueue_document", lambda document_id: True
    )

    first = document_service.create_and_start_processing(
        user_id="u",
        organization_id="org-1",
        filename="notes.txt",
        content_type="text/plain",
        data=b"same content",
    )
    assert first["status"] == "pending"

    try:
        document_service.create_and_start_processing(
            user_id="u",
            organization_id="org-1",
            filename="notes-renamed.txt",
            content_type="text/plain",
            data=b"same content",
        )
        raise AssertionError("expected duplicate rejection")
    except ConflictError:
        pass

    # A different organization may still upload the identical content.
    second = document_service.create_and_start_processing(
        user_id="u",
        organization_id="org-2",
        filename="notes.txt",
        content_type="text/plain",
        data=b"same content",
    )
    assert second["organization_id"] == "org-2"
    assert len(repo.created) == 2


def test_duplicate_race_maps_unique_violation_to_conflict(monkeypatch):
    """If the pre-check misses a concurrent insert, the unique index raises
    and must still surface as ConflictError, not a raw 500."""

    class RaceRepo(FakeRepo):
        def get_by_checksum(self, organization_id, checksum):
            return None

        def create(self, data):
            raise RuntimeError(
                "duplicate key value violates unique constraint "
                '"documents_org_checksum_idx"'
            )

    repo = RaceRepo()
    monkeypatch.setattr(document_service, "DocumentRepository", lambda: repo)

    try:
        document_service.create_and_start_processing(
            user_id="u",
            organization_id="org-1",
            filename="notes.txt",
            content_type="text/plain",
            data=b"same content",
        )
        raise AssertionError("expected duplicate rejection")
    except ConflictError:
        pass
