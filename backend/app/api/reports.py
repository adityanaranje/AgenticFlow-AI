"""Report routes (Phase 1 placeholder).

Report generation and retrieval endpoints are implemented in a
later phase.
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["reports"],
)
