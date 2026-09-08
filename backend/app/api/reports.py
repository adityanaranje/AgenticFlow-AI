"""Reports API (Phase 5, §13). Org-scoped with membership enforcement."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import Membership
from app.core.rbac import require_admin, require_viewer
from app.db.repositories.reports import ReportRepository

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/reports",
    tags=["reports"],
)


@router.get("")
def list_reports(
    organization_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    rows = ReportRepository().list_for_org(organization_id)
    return {"reports": rows}


@router.get("/{report_id}")
def get_report(
    organization_id: str,
    report_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    report = ReportRepository().get(report_id, organization_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    sources = ReportRepository().list_sources(report_id)
    return {"report": report, "sources": sources}


@router.delete("/{report_id}")
def delete_report(
    organization_id: str,
    report_id: str,
    membership: Membership = Depends(require_admin()),
) -> dict:
    repo = ReportRepository()
    if repo.get(report_id, organization_id) is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    repo.delete(report_id, organization_id)
    return {"deleted": True}
