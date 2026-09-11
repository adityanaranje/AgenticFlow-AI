"""Document ingestion API (Phase 4, §3).

Routes are scoped under ``/api/v1/organizations/{organization_id}/documents``
so every handler resolves the caller's membership from the path org first and
never trusts a client-supplied ``organization_id`` or document ownership.

    POST   /organizations/{organization_id}/documents/upload
    GET    /organizations/{organization_id}/documents
    GET    /organizations/{organization_id}/documents/{document_id}
    GET    /organizations/{organization_id}/documents/{document_id}/chunks
    GET    /organizations/{organization_id}/documents/{document_id}/retrieve
    DELETE /organizations/{organization_id}/documents/{document_id}

Upload accepts a ``multipart/form-data`` ``file`` field. Storage paths are
derived server-side and processing is enqueued on Redis (inline fallback).

Role gates mirror the RLS policies: any member may read/retrieve, a
researcher+ may upload, an admin+ may delete.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.auth import Membership
from app.core.exceptions import ConflictError, ValidationError
from app.core.logging import get_logger
from app.core.rbac import require_admin, require_researcher, require_viewer
from app.db.repositories.documents import DocumentRepository
from app.services import document_service, retrieval

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/documents",
    tags=["documents"],
)

_NOT_FOUND = HTTPException(status_code=404, detail="Document not found.")


@router.post("/upload", status_code=201)
async def upload_document(
    organization_id: str,
    file: UploadFile = File(...),
    membership: Membership = Depends(require_researcher()),
) -> dict:
    """Upload a document and start (background) processing.

    Requires researcher+ (contributing action, mirrors RLS insert policy).
    """
    filename = (file.filename or "").strip() or "document"
    content_type = file.content_type or "application/octet-stream"
    data = await file.read()

    try:
        record = document_service.create_and_start_processing(
            user_id=membership.user.id,
            organization_id=organization_id,
            filename=filename,
            content_type=content_type,
            data=data,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        # Always log unexpected failures — the real cause must be visible in
        # the server log, not just as an opaque 500 in the browser.
        logger.exception(
            "Document upload failed (org=%s, file=%s).",
            organization_id,
            filename,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"document": record, "message": "Document uploaded."}


@router.get("")
def list_documents(
    organization_id: str,
    status: str | None = Query(default=None, description="Filter by status"),
    membership: Membership = Depends(require_viewer()),
) -> dict:
    """List documents for the caller's organization (any member may view)."""
    repository = DocumentRepository()
    documents = repository.list_for_organization(organization_id)
    if status:
        documents = [d for d in documents if d.get("status") == status]
    return {"documents": documents}


@router.get("/{document_id}")
def get_document(
    organization_id: str,
    document_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    """Return a single document (must belong to the caller's org)."""
    record = DocumentRepository().get_by_id(document_id, organization_id)
    if record is None:
        raise _NOT_FOUND
    return {"document": record}


@router.get("/{document_id}/chunks")
def list_document_chunks(
    organization_id: str,
    document_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    """Return the stored chunks for a document (DB rows)."""
    record = DocumentRepository().get_by_id(document_id, organization_id)
    if record is None:
        raise _NOT_FOUND
    chunks = DocumentRepository().list_chunks(document_id, organization_id)
    return {"document_id": document_id, "chunks": chunks}


@router.get("/{document_id}/retrieve")
def retrieve_document(
    organization_id: str,
    document_id: str,
    query: str = Query(...),
    top_k: int = Query(default=5, ge=1, le=20),
    membership: Membership = Depends(require_viewer()),
) -> dict:
    """Semantic search scoped to one document within the caller's org."""
    record = DocumentRepository().get_by_id(document_id, organization_id)
    if record is None:
        raise _NOT_FOUND
    results = retrieval.retrieve_context(
        organization_id=organization_id,
        query=query,
        top_k=top_k,
        filters={"document_id": document_id},
    )
    return {"results": results}


@router.delete("/{document_id}")
def delete_document(
    organization_id: str,
    document_id: str,
    membership: Membership = Depends(require_admin()),
) -> dict:
    """Delete a document (admin+): DB row + chunks + storage + Qdrant vectors."""
    from app.services import document_storage, vector_store

    repository = DocumentRepository()
    record = repository.get_by_id(document_id, organization_id)
    if record is None:
        raise _NOT_FOUND

    # Best-effort cleanup of derived data before removing the row.
    try:
        vector_store.delete_document_vectors(organization_id, document_id)
    except Exception:
        pass
    try:
        repository.delete_chunks(document_id, organization_id)
    except Exception:
        pass
    try:
        document_storage.delete_document(
            organization_id, document_id, record.get("filename") or "document"
        )
    except Exception:
        pass

    repository.delete(document_id, organization_id)
    return {"deleted": True}
