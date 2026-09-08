"""Research API (Phase 5, §2/§3).

Org-scoped endpoints. Every handler first resolves the caller's membership
from the path organization. ``user_id`` is derived from the authenticated JWT
— never accepted from the client.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import Membership
from app.core.rbac import require_researcher, require_viewer
from app.db.repositories.research import ResearchRepository
from app.services import research_service

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/research",
    tags=["research"],
)


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    config: dict[str, Any] = Field(default_factory=dict)


@router.post("", status_code=202)
def create_research(
    organization_id: str,
    body: ResearchRequest,
    membership: Membership = Depends(require_researcher()),
) -> dict:
    """Create + enqueue a research run. Returns immediately (202)."""
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query is required.")

    run = research_service.create_research(
        organization_id=organization_id,
        user_id=membership.user.id,  # from JWT, never the client
        question=body.query.strip(),
        config=body.config or {},
    )
    return {
        "id": run["id"],
        "status": run["status"],
        "question": run["question"],
        "created_at": run.get("created_at"),
        "message": "Research queued.",
    }


@router.get("")
def list_research(
    organization_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    rows = ResearchRepository().list_for_org(organization_id)
    return {"research": rows}


@router.get("/{research_id}")
def get_research(
    organization_id: str,
    research_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    run = ResearchRepository().get(research_id, organization_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    return {"research": run}


@router.post("/{research_id}/cancel")
def cancel_research(
    organization_id: str,
    research_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    repo = ResearchRepository()
    run = repo.get(research_id, organization_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found.")

    # Only the owner of the run, or an admin/owner of the org, may cancel.
    is_admin = membership.role in ("owner", "admin")
    if not is_admin and run.get("user_id") != membership.user.id:
        raise HTTPException(status_code=403, detail="Not allowed to cancel this run.")

    research_service.cancel_research(research_id, organization_id)
    return {"id": research_id, "status": "cancelled"}
