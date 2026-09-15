"""Document upload orchestration & validation (Phase 4, §2/§3/§4).

Handles the parts of upload that live outside the worker:

    - file validation (extension + MIME + size; never extension alone)
    - checksum computation
    - creating the document record
    - persisting bytes to private Supabase Storage
    - enqueuing background processing (Redis), with an inline fallback so a
      development environment without Redis still runs the pipeline.

Storage paths are always derived server-side (never client-supplied).
"""

from __future__ import annotations

import hashlib
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from app.core.config import settings
from app.core.exceptions import ConflictError, ValidationError
from app.core.logging import get_logger
from app.db.repositories.documents import DocumentRepository
from app.services import background, document_parser, document_storage, job_queue

logger = get_logger(__name__)

# Canonical type -> readable label used in messages.
_TYPE_LABELS = {"pdf": "PDF", "txt": "plain text", "md": "Markdown", "docx": "Word (DOCX)"}


def compute_checksum(data: bytes) -> str:
    """SHA-256 hex digest of the raw file bytes."""
    return hashlib.sha256(data).hexdigest()


def _is_unique_violation(exc: Exception) -> bool:
    """Best-effort detection of Postgres unique-violation errors (23505)."""
    code = str(getattr(exc, "code", "") or "")
    message = str(exc).lower()
    return (
        code == "23505"
        or "duplicate key" in message
        or "documents_org_checksum" in message
        or "unique constraint" in message
    )


def max_upload_bytes() -> int:
    return settings.max_upload_size_mb * 1024 * 1024


def validate_file_size(size: int) -> None:
    if size < 0:
        raise ValidationError("Invalid file size.")
    if size > max_upload_bytes():
        raise ValidationError(
            f"File is too large. Maximum allowed is {settings.max_upload_size_mb} MB."
        )
    if size == 0:
        raise ValidationError("File is empty.")


def resolve_file_type(filename: str, content_type: str) -> str:
    """Return the canonical supported type or raise ValidationError.

    Never trusts the extension alone: an unsupported extension, an
    unsupported MIME, or an extension/MIME mismatch are all rejected.
    """
    ext = document_parser.extension_of(filename)
    if not ext:
        raise ValidationError(
            "Unsupported file type. Please upload a PDF, TXT, Markdown or DOCX file."
        )

    mime = (content_type or "").strip().lower()

    # No MIME reported / generic octet-stream -> fall back to the extension.
    if not mime or mime in ("application/octet-stream", "binary/octet-stream"):
        return ext

    if mime not in document_parser.SUPPORTED_MIME_TYPES:
        raise ValidationError(
            f"Unsupported file type ({mime}). Please upload a PDF, TXT, "
            "Markdown or DOCX file."
        )

    expected = document_parser.EXTENSION_MIME[ext]
    if mime != expected:
        raise ValidationError(
            f"File type mismatch: the '{ext}' extension does not match the "
            f"reported content type '{mime}'."
        )

    return ext


def _storage_payload(
    filename: str, file_type: str, data: bytes, checksum: str | None = None
) -> dict[str, Any]:
    return {
        "filename": filename,
        "file_type": file_type,
        "file_size": len(data),
        "checksum": checksum or compute_checksum(data),
        "status": "pending",
        "storage_path": "",
    }


def _discard_uploaded_object(
    upload: Future,
    organization_id: str,
    document_id: str,
    filename: str,
) -> None:
    """Best effort: delete stored bytes when the matching DB row was not
    created (duplicate upload / DB error), so a failed request cannot leave
    an orphaned object behind."""
    try:
        upload.result()
    except Exception:
        return  # the upload itself failed — nothing was stored
    try:
        document_storage.delete_document(organization_id, document_id, filename)
    except Exception:
        logger.warning(
            "Could not remove the storage object for an abandoned upload "
            "(org=%s doc=%s).",
            organization_id,
            document_id,
            exc_info=True,
        )


def start_processing(document_id: str) -> bool:
    """Hand a document to the worker queue, with a non-blocking fallback.

    Returns ``True`` when the job was queued on Redis and ``False`` when it
    was dispatched to the in-process background pool instead. Either way the
    caller returns immediately: the HTTP request never waits for the
    ingestion pipeline.
    """
    if job_queue.enqueue_document(document_id):
        return True

    from app.workers.document_worker import process_document

    logger.info(
        "Redis unavailable; processing document %s in the background pool.",
        document_id,
    )
    background.submit(process_document, document_id)
    return False


def create_and_start_processing(
    *,
    user_id: str,
    organization_id: str,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict[str, Any]:
    """Validate, persist and queue a newly uploaded document.

    Steps:
      1. validate type + size
      2. reject duplicate content for the same organization (409 conflict)
      3. create the document record (status ``pending``) and upload the bytes
         to private storage **concurrently** — the storage path is derived
         server-side, so neither call needs the other's result
      4. enqueue the worker job (or process in the background when Redis is
         absent)

    Returns the newly created document record (status ``pending``); callers
    should not expect a terminal status here — processing happens in the
    worker / background pool and is observed by polling the record.
    """
    validate_file_size(len(data))
    file_type = resolve_file_type(filename, content_type)

    document_id = str(uuid.uuid4())
    checksum = compute_checksum(data)
    storage_path = document_storage.build_storage_path(
        organization_id, document_id, filename
    )

    repository = DocumentRepository()

    # Duplicate guard: the documents table enforces uniqueness of
    # (organization_id, checksum) via ``documents_org_checksum_idx`` —
    # surface a friendly conflict instead of a raw database error (500).
    # The lookup itself is advisory; the unique index remains authoritative.
    existing = None
    try:
        existing = repository.get_by_checksum(organization_id, checksum)
    except Exception:
        logger.warning(
            "Checksum lookup failed for org=%s; proceeding without pre-check.",
            organization_id,
            exc_info=True,
        )

    if existing is not None:
        raise ConflictError(
            "This exact file has already been uploaded to this organization "
            f"(document '{existing.get('filename') or filename}')."
        )

    base = _storage_payload(filename, file_type, data, checksum)
    base.update(
        {
            "id": document_id,
            "organization_id": organization_id,
            "uploaded_by": user_id,
            "storage_path": storage_path,
        }
    )

    mime = document_parser.EXTENSION_MIME[file_type]

    # The record insert and the storage upload are independent (the storage
    # path is derived from ids we already have), so they run together: the
    # upload — usually the slowest call in this request — no longer waits for
    # a database round trip, and vice versa. One extra thread is enough: the
    # caller is already running in the API's thread pool, so ``create`` stays
    # on this thread while the upload happens alongside it.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="upload") as pool:
        upload = pool.submit(
            document_storage.upload_document,
            organization_id,
            document_id,
            filename,
            data,
            mime,
        )

        try:
            record = repository.create(base)
        except Exception as exc:
            _discard_uploaded_object(upload, organization_id, document_id, filename)
            if _is_unique_violation(exc):
                raise ConflictError(
                    "This exact file has already been uploaded to this organization."
                ) from exc
            raise
        if record is None:
            _discard_uploaded_object(upload, organization_id, document_id, filename)
            raise RuntimeError("Could not create the document record.")

        try:
            upload.result()
        except Exception as exc:
            logger.exception("Storage upload failed for document %s", document_id)
            repository.update(
                document_id,
                organization_id,
                {"status": "failed", "processing_error": "Upload to storage failed."},
            )
            raise RuntimeError("Could not store the uploaded file.") from exc

    # Hand off to the worker (Redis) or to the in-process background pool.
    # Either way this returns immediately: upload latency is decoupled from
    # ingestion latency, and the client follows progress by polling status.
    start_processing(document_id)

    return record
