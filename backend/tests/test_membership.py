"""Organization membership rules (Phase 3, §16).

Mirrors the invariants enforced by the database guard trigger in
``database/migrations/015_member_management.sql``, so a regression in the
Python layer is caught without needing a live Postgres.
"""

from typing import Any

import pytest
from app.core.exceptions import AuthorizationError, ConflictError, ValidationError
from app.services.membership import (
    MembershipService,
    check_can_act_on,
    check_can_assign_role,
    check_not_last_owner,
    is_invitation_acceptable,
    normalize_email,
    validate_role,
)

# ----------------------------------------------------------------------
# Pure validators
# ----------------------------------------------------------------------


def test_normalize_email_trims_and_lowercases():
    assert normalize_email("  Alice@Example.COM ") == "alice@example.com"


@pytest.mark.parametrize("bad", ["", "   ", "alice", "alice@", "@example.com", "a@b"])
def test_normalize_email_rejects_garbage(bad):
    with pytest.raises(ValidationError):
        normalize_email(bad)


def test_validate_role_accepts_canonical_roles():
    for role in ("owner", "admin", "researcher", "viewer"):
        assert validate_role(role.upper()) == role


@pytest.mark.parametrize("bad", ["", "superuser", "analyst", "root"])
def test_validate_role_rejects_unknown(bad):
    with pytest.raises(ValidationError):
        validate_role(bad)


def test_only_owner_may_grant_owner():
    check_can_assign_role("owner", "owner")
    with pytest.raises(AuthorizationError):
        check_can_assign_role("admin", "owner")


def test_cannot_assign_role_above_your_own():
    check_can_assign_role("admin", "researcher")
    with pytest.raises(AuthorizationError):
        check_can_assign_role("researcher", "admin")


def test_cannot_act_on_higher_ranked_member():
    owner = {"user_id": "u-owner", "role": "owner"}
    admin = {"user_id": "u-admin", "role": "admin"}

    with pytest.raises(AuthorizationError):
        check_can_act_on("admin", "u-admin", owner)

    # An owner may act on an admin, and anyone may act on themselves.
    check_can_act_on("owner", "u-owner", admin)
    check_can_act_on("admin", "u-admin", admin)


def test_last_owner_is_protected():
    owner = {"user_id": "u1", "role": "owner"}

    with pytest.raises(ConflictError):
        check_not_last_owner(owner, owner_count=1, new_role="admin")

    # Fine when another owner remains, or when the role is unchanged.
    check_not_last_owner(owner, owner_count=2, new_role="admin")
    check_not_last_owner(owner, owner_count=1, new_role="owner")
    check_not_last_owner({"user_id": "u2", "role": "admin"}, owner_count=1)


def test_invitation_acceptance_matching():
    invitation = {"status": "pending", "email": "alice@example.com"}
    assert is_invitation_acceptable(invitation, "Alice@Example.com")
    assert not is_invitation_acceptable(invitation, "bob@example.com")
    assert not is_invitation_acceptable({**invitation, "status": "revoked"}, "alice@example.com")
    assert not is_invitation_acceptable({}, "alice@example.com")


# ----------------------------------------------------------------------
# Service orchestration (fake repository)
# ----------------------------------------------------------------------


class FakeRepository:
    """In-memory stand-in for :class:`OrganizationRepository`."""

    def __init__(self, members: list[dict[str, Any]] | None = None, users=None):
        self.members = members or []
        self.users = users or {}
        self.invitations: list[dict[str, Any]] = []

    def get_member(self, organization_id):
        return [m for m in self.members if m["organization_id"] == organization_id]

    def get_membership(self, organization_id, user_id):
        for m in self.members:
            if m["organization_id"] == organization_id and m["user_id"] == user_id:
                return m
        return None

    def count_owners(self, organization_id):
        return len(
            [
                m
                for m in self.get_member(organization_id)
                if m["role"] == "owner"
            ]
        )

    def add_member(self, organization_id, user_id, role):
        row = {
            "id": f"m-{len(self.members) + 1}",
            "organization_id": organization_id,
            "user_id": user_id,
            "role": role,
        }
        self.members.append(row)
        return row

    def update_member_role(self, organization_id, user_id, role):
        member = self.get_membership(organization_id, user_id)
        if member is None:
            return None
        member["role"] = role
        return member

    def remove_member(self, organization_id, user_id):
        member = self.get_membership(organization_id, user_id)
        if member is None:
            return False
        self.members.remove(member)
        return True

    def find_user_by_email(self, email):
        return self.users.get(email.lower())

    def get_pending_invitation(self, organization_id, email):
        for inv in self.invitations:
            if (
                inv["organization_id"] == organization_id
                and inv["email"] == email.lower()
                and inv["status"] == "pending"
            ):
                return inv
        return None

    def create_invitation(self, organization_id, email, role, invited_by):
        inv = {
            "id": f"i-{len(self.invitations) + 1}",
            "organization_id": organization_id,
            "email": email.lower(),
            "role": role,
            "status": "pending",
            "invited_by": invited_by,
            "token": "tok-123",
        }
        self.invitations.append(inv)
        return inv

    def list_invitations(self, organization_id, status="pending"):
        return [
            i
            for i in self.invitations
            if i["organization_id"] == organization_id
            and (status is None or i["status"] == status)
        ]

    def get_invitation(self, invitation_id):
        return next((i for i in self.invitations if i["id"] == invitation_id), None)

    def revoke_invitation(self, invitation_id):
        inv = self.get_invitation(invitation_id)
        if inv is None or inv["status"] != "pending":
            return None
        inv["status"] = "revoked"
        return inv


ORG = "org-1"


def make_service(**kwargs):
    repo = FakeRepository(
        members=[
            {"id": "m1", "organization_id": ORG, "user_id": "owner-1", "role": "owner"},
            {"id": "m2", "organization_id": ORG, "user_id": "admin-1", "role": "admin"},
            {"id": "m3", "organization_id": ORG, "user_id": "viewer-1", "role": "viewer"},
        ],
        **kwargs,
    )
    return MembershipService(repository=repo), repo


def test_invite_existing_user_adds_them_immediately():
    service, repo = make_service(users={"new@example.com": {"id": "user-9"}})

    result = service.invite_member(ORG, "admin-1", "admin", "New@Example.com", "researcher")

    assert result["status"] == "added"
    assert result["member"]["user_id"] == "user-9"
    assert repo.get_membership(ORG, "user-9")["role"] == "researcher"


def test_invite_unknown_email_creates_pending_invitation():
    service, repo = make_service()

    result = service.invite_member(ORG, "admin-1", "admin", "ghost@example.com", "viewer")

    assert result["status"] == "invited"
    assert result["invitation"]["email"] == "ghost@example.com"
    assert repo.list_invitations(ORG) == [result["invitation"]]


def test_invite_rejects_duplicate_member():
    service, _ = make_service(users={"v@example.com": {"id": "viewer-1"}})

    with pytest.raises(ConflictError):
        service.invite_member(ORG, "admin-1", "admin", "v@example.com", "viewer")


def test_invite_rejects_duplicate_pending_invitation():
    service, _ = make_service()
    service.invite_member(ORG, "admin-1", "admin", "ghost@example.com", "viewer")

    with pytest.raises(ConflictError):
        service.invite_member(ORG, "admin-1", "admin", "ghost@example.com", "viewer")


def test_admin_cannot_invite_an_owner():
    service, _ = make_service()

    with pytest.raises(AuthorizationError):
        service.invite_member(ORG, "admin-1", "admin", "ghost@example.com", "owner")


def test_update_role_happy_path():
    service, repo = make_service()

    service.update_role(ORG, "owner-1", "owner", "viewer-1", "researcher")

    assert repo.get_membership(ORG, "viewer-1")["role"] == "researcher"


def test_cannot_change_own_role():
    service, _ = make_service()

    with pytest.raises(AuthorizationError):
        service.update_role(ORG, "admin-1", "admin", "admin-1", "owner")


def test_admin_cannot_demote_an_owner():
    service, _ = make_service()

    with pytest.raises(AuthorizationError):
        service.update_role(ORG, "admin-1", "admin", "owner-1", "viewer")


def test_cannot_demote_the_last_owner():
    service, repo = make_service()

    # A second owner demoting the sole *other* owner is fine only while two
    # owners exist; once one remains, the demotion is refused.
    service.update_role(ORG, "owner-1", "owner", "admin-1", "owner")
    service.update_role(ORG, "owner-1", "owner", "admin-1", "admin")
    assert repo.count_owners(ORG) == 1

    # owner-1 is now the last owner: another owner-level actor cannot demote
    # them either.
    repo.add_member(ORG, "owner-2", "owner")
    repo.update_member_role(ORG, "owner-2", "owner")
    repo.remove_member(ORG, "owner-2")

    with pytest.raises(ConflictError):
        service.update_role(ORG, "admin-1", "owner", "owner-1", "admin")


def test_self_demotion_is_refused():
    service, _ = make_service()

    with pytest.raises(AuthorizationError):
        service.update_role(ORG, "owner-1", "owner", "owner-1", "admin")


def test_update_role_rejects_non_member():
    service, _ = make_service()

    with pytest.raises(ValidationError):
        service.update_role(ORG, "owner-1", "owner", "nobody", "admin")


def test_remove_member():
    service, repo = make_service()

    service.remove_member(ORG, "admin-1", "admin", "viewer-1")

    assert repo.get_membership(ORG, "viewer-1") is None


def test_admin_cannot_remove_an_owner():
    service, _ = make_service()

    with pytest.raises(AuthorizationError):
        service.remove_member(ORG, "admin-1", "admin", "owner-1")


def test_last_owner_cannot_leave():
    service, _ = make_service()

    with pytest.raises(ConflictError):
        service.remove_member(ORG, "owner-1", "owner", "owner-1")


def test_member_can_leave_voluntarily():
    service, repo = make_service()

    service.remove_member(ORG, "viewer-1", "viewer", "viewer-1")

    assert repo.get_membership(ORG, "viewer-1") is None


def test_revoke_invitation():
    service, repo = make_service()
    result = service.invite_member(ORG, "admin-1", "admin", "ghost@example.com", "viewer")

    service.revoke_invitation(ORG, result["invitation"]["id"])

    assert repo.get_invitation(result["invitation"]["id"])["status"] == "revoked"
    assert repo.list_invitations(ORG, status="pending") == []


def test_revoke_invitation_rejects_other_organizations():
    service, _ = make_service()
    result = service.invite_member(ORG, "admin-1", "admin", "ghost@example.com", "viewer")

    with pytest.raises(ValidationError):
        service.revoke_invitation("org-other", result["invitation"]["id"])
