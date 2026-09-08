"""Document ingestion worker (Phase 4, §6).

Processes a single document end to end:

    1. validate          -> fetch the document record, mark it processing
    2. download          -> pull the raw bytes from Supabase Storage
    3. extract text      -> parser (PDF / DOCX / TXT / MD)
    4. normalize text    -> parser normalizes before chunking
    5. split into chunks -> paragraph-aware recursive chunking
    6. generate vectors  -> OpenAI embeddings
    7. upsert to Qdrant  -> tenant-scoped payloads + DB chunk linkage
    8. update status     -> completed (or failed with a safe message)

Run the consumer directly::

    python -m app.workers.document_worker

Jobs are pushed by the upload API onto a Redis list
(:mod:`app.services.job_queue`).
"""

from __future__ import annotations

import uuid
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import ingestion_span
from app.db.repositories.documents import DocumentRepository
from app.services import chunking, document_parser, document_storage, embeddings
from app.services import job_queue, vector_store

logger = get_logger(__name__)

_EMBED_BATCH = 64


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


def process_document(document_id: str) -> dict:
    """Run the full ingestion pipeline for one document id."""
    repository = DocumentRepository()
    doc = repository.get_document(document_id)

    if doc is None:
        raise ValueError(f"Document {document_id} does not exist.")

    organization_id = doc["organization_id"]
    filename = doc["filename"] or "document"
    file_type = doc["file_type"]

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
            if not parsed.pages or not parsed.full_text.strip():
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

        # 6. embeddings
        contents = [chunk.content for chunk in chunks]
        vectors: list[list[float]] = []
        for start in range(0, len(contents), _EMBED_BATCH):
            batch = contents[start : start + _EMBED_BATCH]
            with ingestion_span(
                "document.embed",
                metadata={
                    "document_id": document_id,
                    "batch_size": len(batch),
                },
            ):
                vectors.extend(embeddings.embed_texts(batch))

        # 7. upsert vectors + persist chunk rows (DB chunk id == point id)
        with ingestion_span(
            "document.vector_upsert",
            metadata={
                "document_id": document_id,
                "chunk_count": len(chunks),
            },
        ):
            vector_store.ensure_collection()
            # Idempotent: drop prior chunk rows + vectors before re-inserting.
            repository.delete_chunks(document_id, organization_id)
            vector_store.delete_document_vectors(organization_id, document_id)

            points = []
            for chunk, vector in zip(chunks, vectors):
                chunk_id = uuid.uuid4()
                payload = {
                    "organization_id": organization_id,
                    "document_id": document_id,
                    "document_chunk_id": str(chunk_id),
                    "filename": filename,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                    "file_type": file_type,
                    "content": chunk.content,
                    "char_count": chunk.char_count,
                    "token_estimate": chunk.token_estimate,
                    "metadata": chunk.metadata,
                }
                repository.create_chunk(
                    {
                        "id": str(chunk_id),
                        "document_id": document_id,
                        "organization_id": organization_id,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "page_number": chunk.page_number,
                        "metadata": chunk.metadata,
                        "vector_point_id": str(chunk_id),
                    }
                )
                points.append(
                    {
                        "id": str(chunk_id),
                        "vector": vector,
                        "payload": payload,
                    }
                )
            vector_store.upsert_chunk_vectors(points)

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
            "Document %s processed: %d chunks, %d pages",
            document_id,
            len(chunks),
            parsed.page_count or 0,
        )
        return {"status": "completed", "chunk_count": len(chunks)}

    except Exception as exc:
        logger.exception("Document processing failed for %s", document_id)
        _mark_failed(document_id, organization_id, str(exc))
        return {"status": "failed", "error": str(exc)}


def run_worker(interval: Optional[int] = None) -> None:
    """Blocking consumer loop. Polls Redis for jobs and processes them."""
    wait = interval if interval is not None else 5
    logger.info("Document worker started (queue=%s).", job_queue.QUEUE_NAME)

    while True:
        document_id = job_queue.pop_next(timeout=wait)
        if not document_id:
            continue
        try:
            process_document(document_id)
        except Exception:
            logger.exception("Unhandled worker error for document %s", document_id)


def main() -> None:
    run_worker()


if __name__ == "__main__":
    main()
