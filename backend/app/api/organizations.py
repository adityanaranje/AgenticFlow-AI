"""Organization routes (Phase 3, Part B §9/§15/§16).

Every endpoint authorizes the caller through the Supabase session before
touching data:

    - listing requires an authenticated user (``get_current_user``),
    - reading a single organization / its members requires a validated
      membership (``require_organization_membership``),
    - management endpoints (added in later phases) layer role checks from
      :mod:`app.core.rbac` on top.

Organization ids supplied by clients are validated against the membership
table — they are never trusted blindly. Note the frontend creates
organizations through ``create_organization`` (the secured Phase-2 DB
function) rather than through this router, so the owner membership is always
created under the authenticated identity server-side.
"""

from fastapi import APIRouter, Depends

from app.core.auth import (
    AuthenticatedUser,
    Membership,
    get_current_user,
    require_organization_membership,
)
from app.core.rbac import require_viewer
from app.db.repositories.organizations import OrganizationRepository

router = APIRouter(
    prefix="/api/v1/organizations",
    tags=["organizations"],
)


@router.get("")
def list_my_organizations(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """List the organizations the authenticated user belongs to."""
    repository = OrganizationRepository()
    memberships = repository.get_for_user(user.id) or []

    return {
        "memberships": memberships,
    }


@router.get("/{organization_id}")
def get_organization(
    organization_id: str,
    membership: Membership = Depends(require_organization_membership),
) -> dict:
    """Return an organization the caller belongs to (with role + members).

    Non-members are rejected with 403 before any tenant data is returned.
    """
    repository = OrganizationRepository()
    members = repository.get_member(organization_id) or []

    return {
        "organization_id": organization_id,
        "role": membership.role,
        "members": members,
    }


@router.get("/{organization_id}/members")
def list_organization_members(
    organization_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    """List members of an organization (any validated member may view)."""
    repository = OrganizationRepository()
    members = repository.get_member(organization_id) or []

    return {
        "organization_id": organization_id,
        "role": membership.role,
        "members": members,
    }
