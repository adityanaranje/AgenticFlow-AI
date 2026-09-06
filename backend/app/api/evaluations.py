"""Evaluation routes (Phase 1 placeholder).

Answer-quality evaluation endpoints are implemented in a later
phase on top of the evaluation data model.
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/evaluations",
    tags=["evaluations"],
)
