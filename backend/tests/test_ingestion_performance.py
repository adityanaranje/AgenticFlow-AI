"""Throughput contracts for document ingestion.

Ingestion wall-clock time is dominated by remote calls (OpenAI embeddings,
PostgREST, Qdrant, Supabase Storage). These tests pin down the properties
that keep it fast — batching, bounded concurrency, overlapping independent
writes, and never blocking an HTTP request on the pipeline — without
asserting on wall-clock durations (which would be flaky in CI).
"""

import threading
import time

import pytest
from app.api import documents as documents_api
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.services import background, document_service, embeddings
from app.services.document_parser import ParsedPage
from app.workers import document_worker


# --------------------------------------------------------------------------
# helpers / fakes
# --------------------------------------------------------------------------
class BulkRepo:
    """Repository double with the bulk chunk-insert helper."""

    def __init__(self, record):
        self.record = dict(record)
        self.created_batches = []
        self.created_chunks = []
        self.updates = []
        self.deleted_chunks = 0

    def get_document(self, document_id):
        return dict(self.record) if document_id == self.record["id"] else None

    def update(self, document_id, organization_id, fields):
        self.updates.append(dict(fields))
        self.record.update(fields)
        return dict(self.record)

    def delete_chunks(self, document_id, organization_id):
        self.deleted_chunks += 1

    def create_chunks(self, rows):
        self.created_batches.append(list(rows))
        self.created_chunks.extend(rows)
        return [{"id": row["id"]} for row in rows]

    def create_chunk(self, row):  # pragma: no cover - must not be used
        raise AssertionError("bulk insert must be preferred when available")


class SlowRepo(BulkRepo):
    """Bulk repo whose inserts block until the vector upsert has started."""

    def __init__(self, record, other_started, self_started):
        super().__init__(record)
        self._other_started = other_started
        self._self_started = self_started

    def create_chunks(self, rows):
        self._self_started.set()
        assert self._other_started.wait(10), "DB insert did not overlap the vector upsert"
        return super().create_chunks(rows)


class RecordingVectorStore:
    def __init__(self, on_upsert=None):
        self.upserts = []
        self.kwargs = []
        self.ensured = 0
        self.deletes = []

    def ensure_collection(self, client=None):
        self.ensured += 1

    def delete_document_vectors(self, organization_id, document_id):
        self.deletes.append((organization_id, document_id))

    def upsert_chunk_vectors(self, points, client=None, **kwargs):
        self.upserts.append(points)
        self.kwargs.append(kwargs)


def _doc(document_id="doc-1", org="org-A"):
    return {
        "id": document_id,
        "organization_id": org,
        "filename": "report.txt",
        "file_type": "txt",
        "status": "pending",
        "storage_path": f"organizations/{org}/documents/{document_id}/report.txt",
    }


def _parsed(paragraphs: int = 60):
    from app.services.document_parser import ParsedDocument

    text = "\n\n".join(
        f"Paragraph {index} explains tenant isolation and retrieval quality in detail."
        * 2
        for index in range(paragraphs)
    )
    return ParsedDocument(
        filename="report.txt", file_type="txt", pages=[ParsedPage(text=text)]
    )


def _wire_worker(monkeypatch, repo, store, parsed=None, vectors=None):
    """Patch the worker's external boundaries with doubles."""
    monkeypatch.setattr(document_worker, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(
        document_worker.document_storage, "download_document", lambda o, d, f: b"bytes"
    )
    monkeypatch.setattr(
        document_worker.document_parser,
        "parse_document",
        lambda d, file_type=None, filename="": parsed or _parsed(),
    )

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return vectors if vectors is not None else [[0.1] * 3 for _ in texts]

    monkeypatch.setattr(document_worker.embeddings, "embed_texts", fake_embed)
    monkeypatch.setattr(
        document_worker.vector_store, "ensure_collection", store.ensure_collection
    )
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


# --------------------------------------------------------------------------
# worker: batching, concurrency, overlap
# --------------------------------------------------------------------------
def test_chunk_rows_are_inserted_in_bulk_batches(monkeypatch):
    """One insert request per batch instead of one per chunk."""
    repo = BulkRepo(_doc())
    store = RecordingVectorStore()
    _wire_worker(monkeypatch, repo, store)
    monkeypatch.setattr(settings, "chunk_insert_batch_size", 5)

    result = document_worker.process_document("doc-1")
    assert result["status"] == "completed"

    assert len(repo.created_chunks) == result["chunk_count"] > 5
    # every batch respects the configured size, and nothing was lost
    assert all(len(batch) <= 5 for batch in repo.created_batches)
    assert sum(len(batch) for batch in repo.created_batches) == result["chunk_count"]
    assert len(repo.created_batches) == -(-result["chunk_count"] // 5)
    assert [row["chunk_index"] for row in repo.created_chunks] == list(
        range(result["chunk_count"])
    )


def test_chunk_rows_fall_back_to_per_row_inserts(monkeypatch):
    """Repositories without the bulk helper keep working (no regression)."""

    class PerRowRepo(BulkRepo):
        create_chunks = None  # type: ignore[assignment]

        def create_chunk(self, row):
            self.created_chunks.append(row)
            return row

    repo = PerRowRepo(_doc())
    store = RecordingVectorStore()
    _wire_worker(monkeypatch, repo, store)

    result = document_worker.process_document("doc-1")
    assert result["status"] == "completed"
    assert len(repo.created_chunks) == result["chunk_count"]


def test_embeddings_use_batched_helper_and_vector_upsert_skips_reensure(monkeypatch):
    """The worker embeds through the batched helper and does not re-ensure the
    collection (the extra ``get_collections`` round trip is redundant)."""
    repo = BulkRepo(_doc())
    store = RecordingVectorStore()
    _wire_worker(monkeypatch, repo, store)

    calls = []
    monkeypatch.setattr(
        document_worker.embeddings,
        "embed_texts_batched",
        lambda texts, **kwargs: calls.append(list(texts)) or [[0.2] * 3 for _ in texts],
    )

    result = document_worker.process_document("doc-1")
    assert result["status"] == "completed"
    # one call for the whole document (batching happens inside the helper)
    assert len(calls) == 1
    assert len(calls[0]) == result["chunk_count"]
    assert store.ensured == 1
    assert store.kwargs and all(kw.get("ensure") is False for kw in store.kwargs)


def test_chunk_rows_and_vectors_are_written_concurrently(monkeypatch):
    """The DB insert and the Qdrant upsert are independent — they overlap."""
    upsert_started = threading.Event()
    insert_started = threading.Event()

    repo = SlowRepo(_doc(), upsert_started, insert_started)
    store = RecordingVectorStore()

    def upsert(points, client=None, **kwargs):
        upsert_started.set()
        assert insert_started.wait(10), "vector upsert did not overlap the DB insert"
        store.upserts.append(points)

    _wire_worker(monkeypatch, repo, store)
    monkeypatch.setattr(document_worker.vector_store, "upsert_chunk_vectors", upsert)

    result = document_worker.process_document("doc-1")
    assert result["status"] == "completed"
    assert len(store.upserts[0]) == result["chunk_count"]


def test_chunk_ids_link_db_rows_to_vector_points(monkeypatch):
    repo = BulkRepo(_doc())
    store = RecordingVectorStore()
    _wire_worker(monkeypatch, repo, store)

    document_worker.process_document("doc-1")

    row_ids = {row["id"] for row in repo.created_chunks}
    point_ids = {point["id"] for point in store.upserts[0]}
    assert row_ids == point_ids
    assert all(row["vector_point_id"] == row["id"] for row in repo.created_chunks)
    assert all(
        point["payload"]["document_chunk_id"] == point["id"]
        for point in store.upserts[0]
    )


def test_worker_runs_jobs_on_multiple_threads(monkeypatch):
    """Several queued documents are processed in parallel, not one by one."""
    import app.services.job_queue as job_queue

    jobs = [f"doc-{i}" for i in range(4)]
    lock = threading.Lock()

    def pop_next(timeout=0):
        with lock:
            return jobs.pop(0) if jobs else None

    monkeypatch.setattr(job_queue, "pop_next", pop_next)

    started = threading.Event()
    release = threading.Event()
    active = 0
    max_active = 0

    def process(document_id):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        started.set()
        release.wait(10)
        with lock:
            active -= 1

    monkeypatch.setattr(document_worker, "process_document", process)
    monkeypatch.setattr(settings, "document_worker_concurrency", 3)

    thread = threading.Thread(
        target=document_worker.run_worker,
        kwargs={"interval": 1, "concurrency": 3},
        daemon=True,
    )
    thread.start()
    try:
        assert started.wait(10), "worker threads never picked up a job"
        # Give the remaining threads a chance to pick up further jobs.
        deadline = time.time() + 5
        while time.time() < deadline and max_active < 3:
            time.sleep(0.05)
        assert max_active >= 3, f"jobs ran sequentially (max concurrency {max_active})"
    finally:
        release.set()
        # The consumer threads are daemons that exit with the process; the
        # job list is empty, so they simply keep polling.
        assert thread.is_alive()


# --------------------------------------------------------------------------
# embeddings helper
# --------------------------------------------------------------------------
def test_embed_texts_batched_preserves_order_and_splits_batches(monkeypatch):
    seen = []

    def fake(texts):
        seen.append(list(texts))
        return [[float(len(texts))] for _ in texts]

    monkeypatch.setattr(embeddings, "embed_texts", fake)
    texts = [f"chunk-{i}" for i in range(10)]
    vectors = embeddings.embed_texts_batched(
        texts, batch_size=4, concurrency=3, max_retries=1
    )

    assert [len(batch) for batch in seen] == [4, 4, 2]
    assert len(vectors) == len(texts)
    assert all(vector == [float(size)] for size, vector in zip([4, 4, 4, 4, 4, 4, 4, 4, 2, 2], vectors))


def test_embed_texts_batched_single_batch_runs_without_pool(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[0.0] for _ in texts])
    assert embeddings.embed_texts_batched(["a"], batch_size=64) == [[0.0]]
    assert embeddings.embed_texts_batched([]) == []


def test_embed_texts_batched_overlaps_requests(monkeypatch):
    """Batches are in flight at the same time (embeddings are pure I/O wait)."""
    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake(texts):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.1)
        with lock:
            active -= 1
        return [[0.0] for _ in texts]

    monkeypatch.setattr(embeddings, "embed_texts", fake)
    embeddings.embed_texts_batched(
        [f"text-{i}" for i in range(32)], batch_size=4, concurrency=4, max_retries=1
    )
    assert max_active > 1, "requests were serialised"


# Named exactly like the openai SDK exceptions: the retry logic classifies
# provider errors by name so it survives SDK module reshuffles.
class RateLimitError(Exception):
    """Mimics openai.RateLimitError — transient, must be retried."""


class BadRequestError(Exception):
    """Mimics openai.BadRequestError — permanent, must not be retried."""


def test_embed_batch_retries_transient_errors(monkeypatch):
    attempts = []

    def flaky(texts):
        attempts.append(1)
        if len(attempts) < 3:
            raise RateLimitError("rate limited")
        return [[0.5] for _ in texts]

    monkeypatch.setattr(embeddings, "embed_texts", flaky)
    monkeypatch.setattr(embeddings, "_sleep", lambda _seconds: None)

    assert embeddings.embed_texts_batched(["x"], max_retries=3) == [[0.5]]
    assert len(attempts) == 3


def test_embed_batch_does_not_retry_permanent_errors(monkeypatch):
    attempts = []

    def broken(texts):
        attempts.append(1)
        raise BadRequestError("invalid input")

    monkeypatch.setattr(embeddings, "embed_texts", broken)

    with pytest.raises(BadRequestError):
        embeddings.embed_texts_batched(["x"], max_retries=3)
    assert len(attempts) == 1


def test_embed_batch_gives_up_after_max_retries(monkeypatch):
    attempts = []

    def always_limited(texts):
        attempts.append(1)
        raise RateLimitError("rate limited")

    monkeypatch.setattr(embeddings, "embed_texts", always_limited)
    monkeypatch.setattr(embeddings, "_sleep", lambda _seconds: None)

    with pytest.raises(RateLimitError):
        embeddings.embed_texts_batched(["x"], max_retries=2)
    assert len(attempts) == 2


# --------------------------------------------------------------------------
# upload path
# --------------------------------------------------------------------------
class _FakeUpload:
    """Minimal stand-in for fastapi's UploadFile."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0
        self.reads = 0

    async def read(self, size: int = -1) -> bytes:
        self.reads += 1
        if size is None or size < 0:
            piece = self._data[self._pos :]
        else:
            piece = self._data[self._pos : self._pos + size]
        self._pos += len(piece)
        return piece


@pytest.mark.asyncio
async def test_read_upload_rejects_oversized_file_early(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    upload = _FakeUpload(b"x" * (5 * 1024 * 1024))

    with pytest.raises(ValidationError):
        await documents_api._read_upload(upload)

    # Stopped reading as soon as the limit was crossed — the remaining
    # megabytes were never materialised.
    assert upload.reads <= 3
    assert upload._pos <= 2 * 1024 * 1024


@pytest.mark.asyncio
async def test_read_upload_returns_bytes_under_the_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 5)
    data = b"hello world"
    assert await documents_api._read_upload(_FakeUpload(data)) == data


class UploadRepo:
    def __init__(self):
        self.created = []
        self.records = {}
        self.updates = []

    def create(self, data):
        row = dict(data)
        self.records[row["id"]] = row
        self.created.append(row)
        return row

    def get_by_id(self, document_id, organization_id):
        return self.records.get(document_id)

    def get_by_checksum(self, organization_id, checksum):
        return None

    def update(self, document_id, organization_id, fields):
        self.updates.append(fields)
        self.records[document_id].update(fields)
        return self.records[document_id]


def test_upload_overlaps_record_insert_with_storage_upload(monkeypatch):
    """The storage upload and the DB insert wait on different services, so
    they run at the same time instead of back to back."""
    repo = UploadRepo()
    insert_started = threading.Event()
    upload_started = threading.Event()

    original_create = repo.create

    def slow_create(data):
        insert_started.set()
        assert upload_started.wait(10), "the storage upload never overlapped"
        return original_create(data)

    def slow_upload(organization_id, document_id, filename, data, content_type="x"):
        upload_started.set()
        assert insert_started.wait(10), "the DB insert never overlapped"
        return f"organizations/{organization_id}/documents/{document_id}/{filename}"

    monkeypatch.setattr(document_service, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(repo, "create", slow_create)
    monkeypatch.setattr(document_service.document_storage, "upload_document", slow_upload)
    monkeypatch.setattr(document_service.job_queue, "enqueue_document", lambda _id: True)

    record = document_service.create_and_start_processing(
        user_id="user-1",
        organization_id="org-A",
        filename="notes.txt",
        content_type="text/plain",
        data=b"contents",
    )
    assert record["status"] == "pending"
    assert len(repo.created) == 1


def test_upload_dispatches_processing_instead_of_running_it(monkeypatch):
    """Without Redis the pipeline is dispatched to the background pool and the
    upload response does not wait for it."""
    repo = UploadRepo()
    dispatched = []

    monkeypatch.setattr(document_service, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(
        document_service.document_storage,
        "upload_document",
        lambda o, d, f, data, content_type="x": f"organizations/{o}/documents/{d}/{f}",
    )
    monkeypatch.setattr(document_service.job_queue, "enqueue_document", lambda _id: False)
    monkeypatch.setattr(
        document_service.background,
        "submit",
        lambda func, *args, **kwargs: dispatched.append((func, args)),
    )

    record = document_service.create_and_start_processing(
        user_id="user-1",
        organization_id="org-A",
        filename="notes.txt",
        content_type="text/plain",
        data=b"contents",
    )

    assert record["status"] == "pending"
    assert len(dispatched) == 1
    # The dispatched callable is the real pipeline, not a stub, and it was
    # handed this document id.
    assert dispatched[0][1] == (record["id"],)
    assert dispatched[0][0].__module__ == "app.workers.document_worker"


def test_duplicate_upload_removes_the_orphaned_storage_object(monkeypatch):
    """A racing duplicate leaves no orphaned object in storage."""
    repo = UploadRepo()
    deleted = []

    def racing_create(data):
        raise RuntimeError(
            'duplicate key value violates unique constraint "documents_org_checksum_idx"'
        )

    monkeypatch.setattr(document_service, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(
        document_service.document_storage,
        "upload_document",
        lambda o, d, f, data, content_type="x": f"organizations/{o}/documents/{d}/{f}",
    )
    monkeypatch.setattr(
        document_service.document_storage,
        "delete_document",
        lambda o, d, f: deleted.append((o, d, f)),
    )
    monkeypatch.setattr(repo, "create", racing_create)
    monkeypatch.setattr(document_service.job_queue, "enqueue_document", lambda _id: True)

    from app.core.exceptions import ConflictError

    with pytest.raises(ConflictError):
        document_service.create_and_start_processing(
            user_id="user-1",
            organization_id="org-A",
            filename="notes.txt",
            content_type="text/plain",
            data=b"same content",
        )

    assert len(deleted) == 1
    assert deleted[0][0] == "org-A"


# --------------------------------------------------------------------------
# background pool
# --------------------------------------------------------------------------
def test_background_wait_idle_reports_drained_pool():
    marker = []

    def work():
        time.sleep(0.05)
        marker.append("done")

    background.submit(work)
    assert background.wait_idle(timeout=10) is True
    assert marker == ["done"]


def test_background_submit_never_raises_into_the_caller():
    def boom():
        raise RuntimeError("ingestion blew up")

    background.submit(boom)  # logged, not raised
    assert background.wait_idle(timeout=10) is True

class _FakeTime:
    """Deterministic stand-in for the worker's ``time`` module reference."""

    def __init__(self, advance_per_call: float = 0.0):
        self._now = 0.0
        self._advance = advance_per_call
        self.slept: list[float] = []

    def monotonic(self) -> float:
        # Each read advances the clock, modelling time spent in the pop.
        self._now += self._advance
        return self._now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


def test_worker_backs_off_when_the_queue_cannot_block(monkeypatch):
    """Without Redis ``pop_next`` returns instantly: the consumer must sleep
    instead of spinning at full CPU."""
    import app.services.job_queue as job_queue

    fake_time = _FakeTime()
    monkeypatch.setattr(document_worker, "time", fake_time)
    monkeypatch.setattr(job_queue, "pop_next", lambda timeout=0: None)

    assert document_worker._pop_with_backoff(2) is None
    assert fake_time.slept == [2]


def test_worker_does_not_double_sleep_after_a_blocking_pop(monkeypatch):
    """With Redis the BLPOP already waited; no extra sleep is added."""
    import app.services.job_queue as job_queue

    fake_time = _FakeTime(advance_per_call=2.0)  # the blocking wait elapsed
    monkeypatch.setattr(document_worker, "time", fake_time)
    monkeypatch.setattr(job_queue, "pop_next", lambda timeout=0: None)

    assert document_worker._pop_with_backoff(2) is None
    assert fake_time.slept == []


def test_worker_returns_the_job_without_sleeping(monkeypatch):
    import app.services.job_queue as job_queue

    fake_time = _FakeTime()
    monkeypatch.setattr(document_worker, "time", fake_time)
    monkeypatch.setattr(job_queue, "pop_next", lambda timeout=0: "doc-9")

    assert document_worker._pop_with_backoff(2) == "doc-9"
    assert fake_time.slept == []
