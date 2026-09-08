"""Supabase Storage helpers for document files (Phase 4, §3/§4).

The FastAPI backend is the only place that writes to the private
``documents`` bucket (via the service-role client, which is never exposed to
the browser). Storage paths are always derived server-side:

    organizations/{organization_id}/documents/{document_id}/{filename}

Arbitrary client-supplied paths are never accepted.
"""

from __future__ import annotations

from urllib.parse import quote

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.db.supabase import get_supabase

logger = get_logger(__name__)

BUCKET = settings.storage_bucket or "documents"


def _storage():
    client = get_supabase()
    if client is None:
        raise ExternalServiceError(
            "Supabase is not configured; cannot access storage."
        )
    return client.storage.from_(BUCKET)


def build_storage_path(organization_id: str, document_id: str, filename: str) -> str:
    """Deterministic, safely-encoded storage path for a document."""
    safe_name = quote(filename, safe="._-")
    return f"organizations/{organization_id}/documents/{document_id}/{safe_name}"


def upload_document(
    organization_id: str,
    document_id: str,
    filename: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload raw bytes and return the storage path."""
    path = build_storage_path(organization_id, document_id, filename)
    _storage().upload(
        path,
        data,
        {"content-type": content_type, "upsert": "true"},
    )
    logger.info(
        "Uploaded document bytes to storage (org=%s doc=%s)",
        organization_id,
        document_id,
    )
    return path


def download_document(organization_id: str, document_id: str, filename: str) -> bytes:
    """Download a document's bytes from storage."""
    path = build_storage_path(organization_id, document_id, filename)
    data = _storage().download(path)
    if data is None:
        raise ExternalServiceError("Document bytes could not be read from storage.")
    return bytes(data)


def delete_document(organization_id: str, document_id: str, filename: str) -> None:
    """Remove a document's object from storage (best effort)."""
    path = build_storage_path(organization_id, document_id, filename)
    try:
        _storage().remove([path])
    except Exception:
        logger.warning(
            "Failed to remove storage object for doc=%s (may already be gone)",
            document_id,
        )
