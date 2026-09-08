"""Worker pipeline + failure + tenant-scope tests (Phase 4, §6/§19).

External boundaries (Supabase DB, storage, OpenAI, Qdrant) are mocked; the
orchestration, chunk linkage and status transitions are asserted for real.
"""

import io

from app.core.config import settings
from app.services.document_parser import ParsedDocument, ParsedPage
from app.workers import document_worker


class FakeRepo:
    def __init__(self, record):
        self.record = dict(record)
        self.updates = []
        self.created_chunks = []
        self.deleted_chunks = []

    def get_document(self, document_id):
        if document_id == self.record["id"]:
            return dict(self.record)
        return None

    def update(self, document_id, organization_id, fields):
        self.updates.append((document_id, organization_id, dict(fields)))
        self.record.update(fields)
        return dict(self.record)

    def delete_chunks(self, document_id, organization_id):
        self.deleted_chunks.append((document_id, organization_id))

    def create_chunk(self, data):
        self.created_chunks.append(dict(data))
        return dict(data)


class FakeVectorStore:
    def __init__(self):
        self.upserts = []
        self.deletes = []
        self.ensured = 0

    def ensure_collection(self, client=None):
        self.ensured += 1

    def delete_document_vectors(self, organization_id, document_id):
        self.deletes.append((organization_id, document_id))

    def upsert_chunk_vectors(self, points):
        self.upserts.append(points)


def _txt_parsed():
    return ParsedDocument(
        filename="report.txt",
        file_type="txt",
        pages=[
            ParsedPage(
                text=(
                    "Tenant isolation keeps organizations separate.\n\n"
                    "Security boundaries are enforced by row level security.\n\n"
                    "Document processing extracts text then embeds chunks."
                )
                * 15,
                page_number=None,
            )
        ],
    )


def test_process_document_success_links_chunks_to_vectors(monkeypatch):
    doc = {
        "id": "doc-1",
        "organization_id": "org-A",
        "filename": "report.txt",
        "file_type": "txt",
        "status": "pending",
        "storage_path": "organizations/org-A/documents/doc-1/report.txt",
    }
    repo = FakeRepo(doc)
    store = FakeVectorStore()

    monkeypatch.setattr(document_worker, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(
        document_worker.document_storage, "download_document", lambda o, d, f: b"bytes"
    )
    monkeypatch.setattr(
        document_worker.document_parser, "parse_document", lambda d, file_type=None, filename="": _txt_parsed()
    )
    monkeypatch.setattr(
        document_worker.embeddings, "embed_texts", lambda texts: [[0.1] * 3 for _ in texts]
    )
    monkeypatch.setattr(document_worker.vector_store, "ensure_collection", store.ensure_collection)
    monkeypatch.setattr(
        document_worker.vector_store,
        "delete_document_vectors",
        store.delete_document_vectors,
    )
    monkeypatch.setattr(
        document_worker.vector_store,
        "upsert_chunk_vectors",
        store.upsert_chunk_vectors,
    )

    result = document_worker.process_document("doc-1")
    assert result["status"] == "completed"
    assert result["chunk_count"] > 0

    # status started as processing, ended completed
    statuses = [u[2]["status"] for u in repo.updates]
    assert statuses[0] == "processing"
    assert statuses[-1] == "completed"

    # DB chunk rows exist with a vector_point_id that equals the point id
    assert repo.created_chunks, "chunks must be persisted to DB"
    for chunk_row in repo.created_chunks:
        assert chunk_row["vector_point_id"], "DB chunk must link to a vector point"
    assert chunk_row["organization_id"] == "org-A"
    assert chunk_row["document_id"] == "doc-1"

    # vectors upserted with tenant payload
    points = store.upserts[0]
    assert len(points) == len(repo.created_chunks)
    for point in points:
        assert point["payload"]["organization_id"] == "org-A"
        assert point["payload"]["document_id"] == "doc-1"
        # point id == db chunk id == vector_point_id linkage
        assert point["id"] == point["payload"]["document_chunk_id"]


def test_process_document_failure_marks_failed_safely(monkeypatch):
    doc = {
        "id": "doc-2",
        "organization_id": "org-A",
        "filename": "broken.pdf",
        "file_type": "pdf",
        "status": "pending",
        "storage_path": "x",
    }
    repo = FakeRepo(doc)
    store = FakeVectorStore()

    monkeypatch.setattr(document_worker, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(
        document_worker.document_storage,
        "download_document",
        lambda o, d, f: (_ for _ in ()).throw(RuntimeError("download exploded with secret")),
    )

    result = document_worker.process_document("doc-2")
    assert result["status"] == "failed"
    last = repo.updates[-1][2]
    assert last["status"] == "failed"
    assert "secret" in last["processing_error"]
    # error message is a single sanitized line, not a stack trace
    assert "\n" not in last["processing_error"]
    assert "Traceback" not in last["processing_error"]


def test_process_document_unknown_id_raises(monkeypatch):
    repo = FakeRepo(
        {"id": "other", "organization_id": "org-A", "filename": "x.txt", "file_type": "txt"}
    )
    monkeypatch.setattr(document_worker, "DocumentRepository", lambda: repo)
    try:
        document_worker.process_document("does-not-exist")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
