"""Research routes (Phase 1 placeholder).

LangGraph agentic research workflow endpoints are implemented in a
later phase; no fake AI functionality is exposed before then.
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/research",
    tags=["research"],
)
