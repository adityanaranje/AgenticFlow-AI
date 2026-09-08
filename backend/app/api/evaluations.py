"""Evaluation API (Phase 5, §20). Org-scoped with membership enforcement."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import Membership
from app.core.rbac import require_researcher, require_viewer
from app.db.repositories.reports import EvaluationRepository, ReportRepository
from app.services.evaluation_service import evaluate_report

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/evaluations",
    tags=["evaluations"],
)


class EvaluateRequest(BaseModel):
    report_id: str


@router.get("")
def list_evaluations(
    organization_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    runs = EvaluationRepository().list_runs(organization_id)
    return {"evaluations": runs}


@router.get("/{run_id}")
def get_evaluation(
    organization_id: str,
    run_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    run = EvaluationRepository().get_run(run_id, organization_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    results = EvaluationRepository().list_results(run_id)
    return {"evaluation": run, "results": results}


@router.post("", status_code=202)
def create_evaluation(
    organization_id: str,
    body: EvaluateRequest,
    membership: Membership = Depends(require_researcher()),
) -> dict:
    """Evaluate an existing report on demand (never modifies it)."""
    report = ReportRepository().get(body.report_id, organization_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    result = evaluate_report(
        organization_id=organization_id,
        report_id=body.report_id,
        test_case=f"report:{body.report_id}",
    )
    if not result:
        raise HTTPException(status_code=500, detail="Evaluation could not run.")
    return {"evaluation_run_id": result.get("evaluation_run_id"), "metrics": result.get("metrics")}
