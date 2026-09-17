"""Organization membership & invitation business rules (Phase 3, §16).

The database is the authoritative boundary (RLS + the
``organization_members_guard`` trigger from migration 015). This module
mirrors those invariants in Python so the API can return clear 400/403/409
responses instead of leaking raw Postgres exceptions, and so the rules are
unit-testable without a live database.

Invariants enforced here and in the database:

* an organization always keeps at least one owner,
* only an owner may grant or revoke the ``owner`` role,
* nobody may change their own role (use "transfer ownership" / "leave"),
* nobody may assign a role above their own, or act on a higher-ranked
  member,
* invitations are issued per-email, expire, and may only be accepted by
  the address they were issued to.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.exceptions import AuthorizationError, ConflictError, ValidationError
from app.core.logging import get_logger
from app.core.rbac import ROLE_HIERARCHY, ROLE_OWNER, ROLE_RANK
from app.db.repositories.organizations import OrganizationRepository

logger = get_logger(__name__)

# Deliberately permissive but structural: the real verification is the
# invitation email itself.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")

ASSIGNABLE_ROLES: tuple[str, ...] = ROLE_HIERARCHY


# ----------------------------------------------------------------------
# Pure validators (no I/O — unit-testable)
# ----------------------------------------------------------------------


def normalize_email(email: str) -> str:
    """Trim + lowercase an email, raising when it is not plausible."""
    candidate = (email or "").strip().lower()

    if not candidate:
        raise ValidationError("An email address is required.")
    if len(candidate) > 320:
        raise ValidationError("That email address is too long.")
    if not _EMAIL_RE.match(candidate):
        raise ValidationError("That does not look like a valid email address.")

    return candidate


def validate_role(role: str) -> str:
    """Ensure ``role`` is one of the canonical organization roles."""
    candidate = (role or "").strip().lower()

    if candidate not in ASSIGNABLE_ROLES:
        raise ValidationError(
            "Role must be one of: " + ", ".join(ASSIGNABLE_ROLES) + "."
        )

    return candidate


def check_can_assign_role(actor_role: str, target_role: str) -> None:
    """An actor may never grant a role above their own, and only an owner
    may grant ``owner``."""
    if target_role == ROLE_OWNER and actor_role != ROLE_OWNER:
        raise AuthorizationError("Only an owner may grant the owner role.")

    if ROLE_RANK.get(target_role, 0) > ROLE_RANK.get(actor_role, 0):
        raise AuthorizationError("You cannot assign a role above your own.")


def check_can_act_on(actor_role: str, actor_id: str, target: dict[str, Any]) -> None:
    """An actor may never modify a member who outranks them, and only an
    owner may modify another owner."""
    target_role = str(target.get("role") or "")
    target_user_id = str(target.get("user_id") or "")

    if target_user_id == actor_id:
        return

    if target_role == ROLE_OWNER and actor_role != ROLE_OWNER:
        raise AuthorizationError("Only an owner may modify another owner.")

    if ROLE_RANK.get(target_role, 0) > ROLE_RANK.get(actor_role, 0):
        raise AuthorizationError(
            "You cannot modify a member with a higher role than your own."
        )


def check_not_last_owner(
    target: dict[str, Any],
    owner_count: int,
    new_role: str | None = None,
) -> None:
    """Block demoting or removing the final owner."""
    if str(target.get("role") or "") != ROLE_OWNER:
        return

    if new_role == ROLE_OWNER:
        return

    if owner_count <= 1:
        raise ConflictError(
            "An organization must always have at least one owner. "
            "Promote another member to owner first."
        )


def is_invitation_acceptable(invitation: dict[str, Any], email: str) -> bool:
    """Whether a pending, unexpired invitation matches ``email``."""
    if not invitation:
        return False
    if invitation.get("status") != "pending":
        return False
    return str(invitation.get("email") or "").lower() == email.strip().lower()


# ----------------------------------------------------------------------
# Orchestration (repository-backed)
# ----------------------------------------------------------------------


class MembershipService:
    """Member & invitation operations for one organization."""

    def __init__(self, repository: OrganizationRepository | None = None) -> None:
        self.repository = repository or OrganizationRepository()

    # -- reads ---------------------------------------------------------

    def list_members(self, organization_id: str) -> list[dict[str, Any]]:
        return self.repository.get_member(organization_id)

    def list_invitations(
        self,
        organization_id: str,
        status: str | None = "pending",
    ) -> list[dict[str, Any]]:
        return self.repository.list_invitations(organization_id, status=status)

    # -- invite / add --------------------------------------------------

    def invite_member(
        self,
        organization_id: str,
        actor_id: str,
        actor_role: str,
        email: str,
        role: str,
    ) -> dict[str, Any]:
        """Invite somebody by email.

        When the address already belongs to a registered user, they are
        added to the organization immediately. Otherwise a pending
        invitation is created and its acceptance link is returned.
        """
        email = normalize_email(email)
        role = validate_role(role)
        check_can_assign_role(actor_role, role)

        existing_user = self.repository.find_user_by_email(email)

        if existing_user and existing_user.get("id"):
            user_id = str(existing_user["id"])

            already = self.repository.get_membership(organization_id, user_id)
            if already:
                raise ConflictError(
                    "That person is already a member of this organization."
                )

            member = self.repository.add_member(organization_id, user_id, role)

            if member is None:
                raise ConflictError("Could not add that member. Please try again.")

            logger.info(
                "Added member to organization org=%s role=%s", organization_id, role
            )
            return {"status": "added", "member": member, "invitation": None}

        pending = self.repository.get_pending_invitation(organization_id, email)
        if pending:
            raise ConflictError(
                "An invitation for that email address is already pending."
            )

        invitation = self.repository.create_invitation(
            organization_id=organization_id,
            email=email,
            role=role,
            invited_by=actor_id,
        )

        if invitation is None:
            raise ConflictError("Could not create the invitation. Please try again.")

        logger.info(
            "Created invitation for organization org=%s role=%s",
            organization_id,
            role,
        )
        return {"status": "invited", "member": None, "invitation": invitation}

    def revoke_invitation(
        self,
        organization_id: str,
        invitation_id: str,
    ) -> dict[str, Any]:
        invitation = self.repository.get_invitation(invitation_id)

        if not invitation or invitation.get("organization_id") != organization_id:
            raise ValidationError("That invitation does not exist.")

        if invitation.get("status") != "pending":
            raise ConflictError("That invitation is no longer pending.")

        revoked = self.repository.revoke_invitation(invitation_id)

        if revoked is None:
            raise ConflictError("Could not revoke that invitation.")

        return revoked

    # -- role changes --------------------------------------------------

    def update_role(
        self,
        organization_id: str,
        actor_id: str,
        actor_role: str,
        target_user_id: str,
        new_role: str,
    ) -> dict[str, Any]:
        new_role = validate_role(new_role)

        if target_user_id == actor_id:
            raise AuthorizationError(
                "You cannot change your own role. Ask another owner or admin."
            )

        target = self.repository.get_membership(organization_id, target_user_id)

        if target is None:
            raise ValidationError("That user is not a member of this organization.")

        if str(target.get("role")) == new_role:
            return target

        check_can_act_on(actor_role, actor_id, target)
        check_can_assign_role(actor_role, new_role)
        check_not_last_owner(
            target,
            self.repository.count_owners(organization_id),
            new_role=new_role,
        )

        updated = self.repository.update_member_role(
            organization_id, target_user_id, new_role
        )

        if updated is None:
            raise ConflictError("Could not update that member's role.")

        logger.info(
            "Updated member role org=%s new_role=%s", organization_id, new_role
        )
        return updated

    # -- removal -------------------------------------------------------

    def remove_member(
        self,
        organization_id: str,
        actor_id: str,
        actor_role: str,
        target_user_id: str,
    ) -> None:
        target = self.repository.get_membership(organization_id, target_user_id)

        if target is None:
            raise ValidationError("That user is not a member of this organization.")

        if target_user_id != actor_id:
            check_can_act_on(actor_role, actor_id, target)

        check_not_last_owner(target, self.repository.count_owners(organization_id))

        removed = self.repository.remove_member(organization_id, target_user_id)

        if not removed:
            raise ConflictError("Could not remove that member.")

        logger.info("Removed member from organization org=%s", organization_id)
