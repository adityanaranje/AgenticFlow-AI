"""Organization routes (Phase 3, Part B §9/§15/§16).

Every endpoint authorizes the caller through the Supabase session before
touching data:

    - listing requires an authenticated user (``get_current_user``),
    - reading a single organization / its members requires a validated
      membership (``require_organization_membership``),
    - management endpoints layer role checks from :mod:`app.core.rbac` on
      top (invite/role changes/removal are admin+).

Organization ids supplied by clients are validated against the membership
table — they are never trusted blindly. Note the frontend creates
organizations through ``create_organization`` (the secured Phase-2 DB
function) rather than through this router, so the owner membership is always
created under the authenticated identity server-side.

Member management routes::

    GET    /organizations/{id}/members
    POST   /organizations/{id}/members            (admin+) invite or add
    PATCH  /organizations/{id}/members/{user_id}  (admin+) change role
    DELETE /organizations/{id}/members/{user_id}  (admin+) remove
    DELETE /organizations/{id}/members/me                  leave
    GET    /organizations/{id}/invitations        (admin+)
    DELETE /organizations/{id}/invitations/{iid}  (admin+) revoke

Business invariants (last owner, self-demotion, rank) live in
:mod:`app.services.membership` and are re-enforced by the database guard
trigger in ``database/migrations/015_member_management.sql``.
"""

from app.api.schemas import InviteMemberRequest, UpdateMemberRoleRequest
from app.core.auth import (
    AuthenticatedUser,
    Membership,
    get_current_user,
    require_organization_membership,
)
from app.core.exceptions import AuthorizationError, ConflictError, ValidationError
from app.core.logging import get_logger
from app.core.rbac import require_admin, require_viewer
from app.db.repositories.organizations import OrganizationRepository
from app.services.membership import MembershipService
from fastapi import APIRouter, Depends, HTTPException, Query, Response

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/organizations",
    tags=["organizations"],
)


def _handle(exc: Exception) -> HTTPException:
    """Map a domain error onto its HTTP status."""
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, AuthorizationError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    logger.exception("Unexpected membership failure.")
    return HTTPException(status_code=500, detail="An unexpected error occurred.")


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


# ----------------------------------------------------------------------
# Members
# ----------------------------------------------------------------------


@router.get("/{organization_id}/members")
def list_organization_members(
    organization_id: str,
    membership: Membership = Depends(require_viewer()),
) -> dict:
    """List members of an organization (any validated member may view)."""
    service = MembershipService()

    return {
        "organization_id": organization_id,
        "role": membership.role,
        "members": service.list_members(organization_id),
    }


@router.post("/{organization_id}/members", status_code=201)
def invite_organization_member(
    organization_id: str,
    payload: InviteMemberRequest,
    membership: Membership = Depends(require_admin()),
) -> dict:
    """Invite somebody to the organization, or add them if they exist.

    Requires admin+ (mirrors the RLS insert policy). Only an owner may
    grant the ``owner`` role, and no one may grant a role above their own.
    """
    service = MembershipService()

    try:
        result = service.invite_member(
            organization_id=organization_id,
            actor_id=membership.user.id,
            actor_role=membership.role,
            email=payload.email,
            role=payload.role,
        )
    except Exception as exc:
        raise _handle(exc) from exc

    return {"organization_id": organization_id, **result}


@router.patch("/{organization_id}/members/{user_id}")
def update_organization_member_role(
    organization_id: str,
    user_id: str,
    payload: UpdateMemberRoleRequest,
    membership: Membership = Depends(require_admin()),
) -> dict:
    """Change a member's role (admin+).

    Guards: you cannot change your own role, assign a role above your own,
    modify a higher-ranked member, or demote the last owner.
    """
    service = MembershipService()

    try:
        member = service.update_role(
            organization_id=organization_id,
            actor_id=membership.user.id,
            actor_role=membership.role,
            target_user_id=user_id,
            new_role=payload.role,
        )
    except Exception as exc:
        raise _handle(exc) from exc

    return {"organization_id": organization_id, "member": member}


@router.delete("/{organization_id}/members/me", status_code=204)
def leave_organization(
    organization_id: str,
    membership: Membership = Depends(require_viewer()),
) -> Response:
    """Leave an organization. The last owner cannot leave."""
    service = MembershipService()

    try:
        service.remove_member(
            organization_id=organization_id,
            actor_id=membership.user.id,
            actor_role=membership.role,
            target_user_id=membership.user.id,
        )
    except Exception as exc:
        raise _handle(exc) from exc

    return Response(status_code=204)


@router.delete("/{organization_id}/members/{user_id}", status_code=204)
def remove_organization_member(
    organization_id: str,
    user_id: str,
    membership: Membership = Depends(require_admin()),
) -> Response:
    """Remove a member from the organization (admin+)."""
    service = MembershipService()

    try:
        service.remove_member(
            organization_id=organization_id,
            actor_id=membership.user.id,
            actor_role=membership.role,
            target_user_id=user_id,
        )
    except Exception as exc:
        raise _handle(exc) from exc

    return Response(status_code=204)


# ----------------------------------------------------------------------
# Invitations
# ----------------------------------------------------------------------


@router.get("/{organization_id}/invitations")
def list_organization_invitations(
    organization_id: str,
    status: str | None = Query(
        "pending",
        description="Filter by status (pending/accepted/revoked); omit for all.",
    ),
    membership: Membership = Depends(require_admin()),
) -> dict:
    """List invitations for an organization (admin+)."""
    service = MembershipService()

    if status not in (None, "", "pending", "accepted", "revoked"):
        raise HTTPException(status_code=400, detail="Unknown invitation status.")

    return {
        "organization_id": organization_id,
        "invitations": service.list_invitations(
            organization_id, status=status or None
        ),
    }


@router.delete("/{organization_id}/invitations/{invitation_id}", status_code=204)
def revoke_organization_invitation(
    organization_id: str,
    invitation_id: str,
    membership: Membership = Depends(require_admin()),
) -> Response:
    """Revoke a pending invitation (admin+)."""
    service = MembershipService()

    try:
        service.revoke_invitation(organization_id, invitation_id)
    except Exception as exc:
        raise _handle(exc) from exc

    return Response(status_code=204)
