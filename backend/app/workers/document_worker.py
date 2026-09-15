"""Document ingestion worker (Phase 4, §6).

Processes a single document end to end:

    1. validate          -> fetch the document record, mark it processing
    2. download          -> pull the raw bytes from Supabase Storage
    3. extract text      -> parser (PDF / DOCX / TXT / MD)
    4. normalize text    -> parser normalizes before chunking
    5. split into chunks -> paragraph-aware recursive chunking
    6. generate vectors  -> OpenAI embeddings (batched + concurrent)
    7. upsert to Qdrant  -> tenant-scoped payloads + DB chunk linkage
    8. update status     -> completed (or failed with a safe message)

Ingestion is I/O bound: nearly all of the wall-clock time is spent waiting
on Supabase Storage, the OpenAI embeddings API, PostgREST and Qdrant. The
pipeline therefore overlaps those remote calls — embeddings are requested in
large parallel batches, chunk rows are inserted in bulk, and vector points
are upserted in parallel batches (the DB insert and the vector upsert run at
the same time as well). Concurrency is bounded by settings so a single
document cannot exhaust provider rate limits.

Run the consumer directly::

    python -m app.workers.document_worker

Jobs are pushed by the upload API onto a Redis list
(:mod:`app.services.job_queue`) and consumed on
``DOCUMENT_WORKER_CONCURRENCY`` threads, so several documents finish in the
time one used to take.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import ingestion_span
from app.db.repositories.documents import DocumentRepository
from app.services import (
    chunking,
    document_parser,
    document_storage,
    embeddings,
    job_queue,
    vector_store,
)

logger = get_logger(__name__)

# Kept for backwards compatibility (older callers/tests import it); the
# effective value now comes from settings.embedding_batch_size.
_EMBED_BATCH = settings.embedding_batch_size


def _mark_failed(document_id: str, organization_id: str, message: str) -> None:
    """Record a failure with a SAFE message (never a stack trace)."""
    safe = (message or "Unknown error").strip().replace("\n", " ")[:1000]
    DocumentRepository().update(
        document_id,
        organization_id,
        {
            "status": "failed",
            "processing_error": safe or "Processing failed.",
        },
    )
    logger.error("Document %s failed: %s", document_id, safe)


def _batched(items: list[Any], size: int) -> Iterable[list[Any]]:
    """Yield ``items`` in lists of at most ``size`` entries."""
    step = max(1, size)
    for start in range(0, len(items), step):
        yield items[start : start + step]


def _chunk_row(
    *,
    document_id: str,
    organization_id: str,
    chunk_id: str,
    chunk: chunking.TextChunk,
) -> dict[str, Any]:
    """DB row for one chunk (id == Qdrant point id == vector_point_id)."""
    return {
        "id": chunk_id,
        "document_id": document_id,
        "organization_id": organization_id,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "page_number": chunk.page_number,
        "metadata": chunk.metadata,
        "vector_point_id": chunk_id,
    }


def _chunk_point(
    *,
    chunk: chunking.TextChunk,
    vector: list[float],
    chunk_id: str,
    document_id: str,
    organization_id: str,
    filename: str,
    file_type: str,
) -> dict[str, Any]:
    """Qdrant point for one chunk (tenant + document + chunk linkage)."""
    return {
        "id": chunk_id,
        "vector": vector,
        "payload": {
            "organization_id": organization_id,
            "document_id": document_id,
            "document_chunk_id": chunk_id,
            "filename": filename,
            "chunk_index": chunk.chunk_index,
            "page_number": chunk.page_number,
            "file_type": file_type,
            "content": chunk.content,
            "char_count": chunk.char_count,
            "token_estimate": chunk.token_estimate,
            "metadata": chunk.metadata,
        },
    }


def _insert_chunk_rows(
    repository: DocumentRepository,
    rows: list[dict[str, Any]],
) -> None:
    """Persist chunk rows in bulk, in parallel batches.

    Falls back to per-row inserts for repositories that do not implement the
    bulk helper (e.g. lightweight test doubles), so behaviour is unchanged
    where batching is unavailable.
    """
    bulk = getattr(repository, "create_chunks", None)
    if not callable(bulk):
        for row in rows:
            repository.create_chunk(row)
        return

    batches = list(_batched(rows, settings.chunk_insert_batch_size))
    if len(batches) == 1:
        bulk(batches[0])
        return

    workers = max(1, min(settings.chunk_insert_concurrency, len(batches)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="chunk-insert") as pool:
        for _ in pool.map(bulk, batches):
            pass


def process_document(document_id: str) -> dict:
    """Run the full ingestion pipeline for one document id."""
    repository = DocumentRepository()
    doc = repository.get_document(document_id)

    if doc is None:
        raise ValueError(f"Document {document_id} does not exist.")

    organization_id = doc["organization_id"]
    filename = doc["filename"] or "document"
    file_type = doc["file_type"]
    started = time.perf_counter()

    try:
        repository.update(
            document_id,
            organization_id,
            {"status": "processing", "processing_error": None},
        )

        # 2. download
        with ingestion_span(
            "document.download",
            metadata={"document_id": document_id, "organization_id": organization_id},
        ):
            raw_bytes = document_storage.download_document(
                organization_id, document_id, filename
            )

        # 3 + 4. extract + normalize text (parser returns normalized pages)
        with ingestion_span(
            "document.parse",
            metadata={"document_id": document_id, "file_type": file_type},
        ):
            parsed = document_parser.parse_document(
                raw_bytes, file_type=file_type, filename=filename
            )
            # Cheap emptiness check: avoids materialising the whole document
            # text (megabytes for large PDFs) just to look for content.
            if not parsed.pages or not any(page.text.strip() for page in parsed.pages):
                raise ValueError("No extractable text found in this document.")

        # 5. chunking
        with ingestion_span(
            "document.chunk",
            metadata={
                "document_id": document_id,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
            },
        ):
            chunks = chunking.chunk_pages(
                parsed.pages,
                extra_metadata={"filename": filename},
            )
            if not chunks:
                raise ValueError("Document produced no usable chunks.")

        # 6. embeddings — one request per batch, several batches in flight.
        contents = [chunk.content for chunk in chunks]
        with ingestion_span(
            "document.embed",
            metadata={
                "document_id": document_id,
                "chunk_count": len(contents),
                "batch_size": settings.embedding_batch_size,
                "concurrency": settings.embedding_concurrency,
            },
        ):
            vectors = embeddings.embed_texts_batched(contents)

        if len(vectors) != len(chunks):
            raise RuntimeError(
                f"Embedding count mismatch: {len(vectors)} vectors for "
                f"{len(chunks)} chunks."
            )

        # 7. persist chunk rows + vectors. Chunk ids are generated locally so
        #    the DB rows and the vector points are keyed by the same id and
        #    both writes can run concurrently.
        chunk_ids = [str(uuid.uuid4()) for _ in chunks]
        rows = [
            _chunk_row(
                document_id=document_id,
                organization_id=organization_id,
                chunk_id=chunk_id,
                chunk=chunk,
            )
            for chunk_id, chunk in zip(chunk_ids, chunks)
        ]
        points = [
            _chunk_point(
                chunk=chunk,
                vector=vector,
                chunk_id=chunk_id,
                document_id=document_id,
                organization_id=organization_id,
                filename=filename,
                file_type=file_type,
            )
            for chunk, vector, chunk_id in zip(chunks, vectors, chunk_ids)
        ]

        with ingestion_span(
            "document.vector_upsert",
            metadata={
                "document_id": document_id,
                "chunk_count": len(chunks),
            },
        ):
            vector_store.ensure_collection()

            # Idempotent: drop prior chunk rows + vectors before re-inserting.
            # The two deletes are independent, so clear them concurrently.
            with ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="ingest-cleanup"
            ) as pool:
                delete_chunks = pool.submit(
                    repository.delete_chunks, document_id, organization_id
                )
                delete_vectors = pool.submit(
                    vector_store.delete_document_vectors,
                    organization_id,
                    document_id,
                )
                delete_chunks.result()
                delete_vectors.result()

            # DB rows and vector points are independent: overlap them.
            with ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="ingest-write"
            ) as pool:
                insert_future = pool.submit(_insert_chunk_rows, repository, rows)
                upsert_future = pool.submit(
                    vector_store.upsert_chunk_vectors, points, None, ensure=False
                )
                insert_future.result()
                upsert_future.result()

        # 8. mark complete
        repository.update(
            document_id,
            organization_id,
            {
                "status": "completed",
                "page_count": parsed.page_count,
                "processing_error": None,
                "metadata": {
                    "chunk_count": len(chunks),
                    "page_count": parsed.page_count,
                },
            },
        )
        logger.info(
            "Document %s processed: %d chunks, %d pages in %.2fs",
            document_id,
            len(chunks),
            parsed.page_count or 0,
            time.perf_counter() - started,
        )
        return {
            "status": "completed",
            "chunk_count": len(chunks),
            "duration_seconds": round(time.perf_counter() - started, 3),
        }

    except Exception as exc:
        logger.exception("Document processing failed for %s", document_id)
        _mark_failed(document_id, organization_id, str(exc))
        return {"status": "failed", "error": str(exc)}


def _pop_with_backoff(wait: int) -> str | None:
    """Pop the next job, backing off when the queue could not block.

    See :func:`app.services.job_queue.pop_with_backoff` (shared with the
    research worker).
    """
    return job_queue.pop_with_backoff(job_queue.pop_next, wait)


# Set by SIGINT/SIGTERM (see :func:`main`) or by tests to stop the consumer
# threads: each thread finishes the document it is processing and exits
# instead of popping another job, so a container stop is graceful.
_STOP = threading.Event()


def _consume_forever(
    worker_id: int, wait: int, stop_event: threading.Event | None = None
) -> None:
    """Pop and process jobs until the process is stopped."""
    stop = stop_event if stop_event is not None else _STOP
    while not stop.is_set():
        document_id = _pop_with_backoff(wait)
        if not document_id:
            continue
        try:
            process_document(document_id)
        except Exception:
            logger.exception(
                "Unhandled worker error for document %s (thread %d)",
                document_id,
                worker_id,
            )


def run_worker(
    interval: int | None = None,
    concurrency: int | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Blocking consumer loop. Polls Redis for jobs and processes them.

    ``concurrency`` documents are processed in parallel (embeddings and
    remote writes are I/O-bound, so threads keep the queue moving). Jobs are
    popped from the shared Redis list, which load-balances naturally.
    Setting ``stop_event`` (or signalling the process) stops the threads once
    the document they are processing finishes.
    """
    wait = interval if interval is not None else settings.document_worker_poll_seconds
    # A blocking BLPOP must return before the Redis client's socket read
    # timeout (3s) fires, otherwise every idle poll raises a socket timeout.
    wait = max(1, min(int(wait), 3))
    workers = max(1, int(concurrency or settings.document_worker_concurrency))

    logger.info(
        "Document worker started (queue=%s, threads=%d, poll=%ss).",
        job_queue.QUEUE_NAME,
        workers,
        wait,
    )

    stop = stop_event if stop_event is not None else _STOP
    threads = [
        threading.Thread(
            target=_consume_forever,
            args=(index, wait, stop),
            name=f"document-worker-{index}",
            daemon=True,
        )
        for index in range(workers)
    ]
    for thread in threads:
        thread.start()

    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:  # pragma: no cover - interactive stop
        logger.info("Document worker interrupted; shutting down.")
        stop.set()


def _install_signal_handlers(stop: threading.Event) -> None:
    """Stop the loops on Ctrl+C / SIGTERM (docker stop) instead of being killed."""
    import signal

    def _handle(signum, _frame):  # pragma: no cover - signal delivery
        logger.info("Document worker received signal %s; finishing current job.", signum)
        stop.set()

    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle)
        except (ValueError, OSError):  # pragma: no cover - non-main thread
            return


def main() -> None:
    _install_signal_handlers(_STOP)
    run_worker()


if __name__ == "__main__":
    main()
