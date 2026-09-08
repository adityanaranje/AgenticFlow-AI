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
from typing import Any

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.db.repositories.documents import DocumentRepository
from app.services import document_parser, document_storage
from app.services import job_queue

logger = get_logger(__name__)

# Canonical type -> readable label used in messages.
_TYPE_LABELS = {"pdf": "PDF", "txt": "plain text", "md": "Markdown", "docx": "Word (DOCX)"}


def compute_checksum(data: bytes) -> str:
    """SHA-256 hex digest of the raw file bytes."""
    return hashlib.sha256(data).hexdigest()


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


def _storage_payload(filename: str, file_type: str, data: bytes) -> dict[str, Any]:
    return {
        "filename": filename,
        "file_type": file_type,
        "file_size": len(data),
        "checksum": compute_checksum(data),
        "status": "pending",
        "storage_path": "",
    }


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
      2. create the document record (status ``pending``)
      3. upload bytes to private storage under the server-derived path
      4. enqueue the worker job (or process inline when Redis is absent)

    Returns the (possibly updated) document record.
    """
    validate_file_size(len(data))
    file_type = resolve_file_type(filename, content_type)

    import uuid

    document_id = str(uuid.uuid4())
    storage_path = document_storage.build_storage_path(
        organization_id, document_id, filename
    )

    base = _storage_payload(filename, file_type, data)
    base.update(
        {
            "id": document_id,
            "organization_id": organization_id,
            "uploaded_by": user_id,
            "storage_path": storage_path,
        }
    )

    repository = DocumentRepository()

    record = repository.create(base)
    if record is None:
        raise RuntimeError("Could not create the document record.")

    try:
        mime = document_parser.EXTENSION_MIME[file_type]
        document_storage.upload_document(
            organization_id, document_id, filename, data, content_type=mime
        )
    except Exception as exc:
        logger.exception("Storage upload failed for document %s", document_id)
        repository.update(
            document_id,
            organization_id,
            {"status": "failed", "processing_error": "Upload to storage failed."},
        )
        raise RuntimeError("Could not store the uploaded file.") from exc

    # Enqueue for background processing; fall back to inline in development
    # when Redis is unavailable so the pipeline still works.
    queued = job_queue.enqueue_document(document_id)
    if not queued:
        from app.workers.document_worker import process_document

        logger.info(
            "Redis unavailable; processing document %s inline.", document_id
        )
        process_document(document_id)

    final = repository.get_by_id(document_id, organization_id)
    return final or record
