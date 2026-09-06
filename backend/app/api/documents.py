"""Document routes (Phase 1 placeholder).

Upload, chunking, embedding and retrieval-backed document endpoints
are implemented in later phases (RAG pipeline).
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["documents"],
)
