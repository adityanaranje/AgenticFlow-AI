"""Executable tests for the member-management guard rules (migration 015).

These run the *real* SQL against a throwaway PostgreSQL instance, so the
database-level invariants are verified rather than assumed:

  * an organization always keeps at least one owner,
  * only an owner may grant or revoke the ``owner`` role,
  * nobody may change their own role or outrank themselves,
  * any member may leave voluntarily,
  * an invitation can only be accepted by the address it was issued to,
    exactly once, before it expires.

Supabase-specific pieces (``auth.users``, ``auth.uid()``, ``auth.jwt()``)
are stubbed by ``conftest.py`` so no Supabase project is required. RLS
policies are not exercised here (they need PostgREST roles) — the guard
trigger and the ``security definer`` functions are.

Run with::

    pip install pgserver psycopg pytest
    pytest database/tests
"""

from __future__ import annotations

import uuid

import pytest


def new_user(db, email: str) -> str:
    user_id = str(uuid.uuid4())
    db.execute(
        "insert into auth.users (id, email) values (%s, %s)", (user_id, email)
    )
    return user_id


@pytest.fixture()
def org(db):
    """An organization owned by ``owner`` with an admin, researcher, viewer."""
    owner = new_user(db, "owner@example.com")
    admin = new_user(db, "admin@example.com")
    viewer = new_user(db, "viewer@example.com")

    db.act_as(owner)
    organization_id = db.fetchone(
        "select id from public.create_organization('Acme', 'acme')"
    )[0]

    # Seeded as the trusted service role (no JWT).
    db.act_as(None)
    for user_id, role in ((admin, "admin"), (viewer, "viewer")):
        db.execute(
            "insert into public.organization_members "
            "(organization_id, user_id, role) values (%s, %s, %s)",
            (organization_id, user_id, role),
        )

    return {
        "id": organization_id,
        "owner": owner,
        "admin": admin,
        "viewer": viewer,
    }


def role_of(db, organization_id, user_id):
    row = db.fetchone(
        "select role from public.organization_members "
        "where organization_id = %s and user_id = %s",
        (organization_id, user_id),
    )
    return row[0] if row else None


# ----------------------------------------------------------------------
# Organization creation
# ----------------------------------------------------------------------


def test_create_organization_makes_the_creator_an_owner(db, org):
    assert role_of(db, org["id"], org["owner"]) == "owner"


# ----------------------------------------------------------------------
# Role changes
# ----------------------------------------------------------------------


def test_admin_can_promote_a_viewer_to_researcher(db, org):
    db.act_as(org["admin"])
    db.execute(
        "update public.organization_members set role = 'researcher' "
        "where organization_id = %s and user_id = %s",
        (org["id"], org["viewer"]),
    )
    assert role_of(db, org["id"], org["viewer"]) == "researcher"


def test_admin_cannot_promote_anyone_to_owner(db, org):
    db.act_as(org["admin"])
    with pytest.raises(Exception, match="Only an owner may grant the owner role"):
        db.execute(
            "update public.organization_members set role = 'owner' "
            "where organization_id = %s and user_id = %s",
            (org["id"], org["viewer"]),
        )


def test_admin_cannot_self_promote(db, org):
    db.act_as(org["admin"])
    with pytest.raises(Exception, match="cannot change your own role"):
        db.execute(
            "update public.organization_members set role = 'owner' "
            "where organization_id = %s and user_id = %s",
            (org["id"], org["admin"]),
        )


def test_admin_cannot_demote_an_owner(db, org):
    # A second owner exists, so the "last owner" rule cannot be what blocks
    # this — the admin is refused purely because they may not touch an owner.
    db.act_as(org["owner"])
    second_owner = new_user(db, "owner2@example.com")
    db.act_as(None)
    db.execute(
        "insert into public.organization_members "
        "(organization_id, user_id, role) values (%s, %s, 'owner')",
        (org["id"], second_owner),
    )

    db.act_as(org["admin"])
    with pytest.raises(Exception, match="Only an owner may modify another owner"):
        db.execute(
            "update public.organization_members set role = 'viewer' "
            "where organization_id = %s and user_id = %s",
            (org["id"], org["owner"]),
        )


def test_owner_can_promote_and_then_be_demoted(db, org):
    db.act_as(org["owner"])
    db.execute(
        "update public.organization_members set role = 'owner' "
        "where organization_id = %s and user_id = %s",
        (org["id"], org["admin"]),
    )
    assert role_of(db, org["id"], org["admin"]) == "owner"

    # With two owners, one may demote the other.
    db.act_as(org["admin"])
    db.execute(
        "update public.organization_members set role = 'admin' "
        "where organization_id = %s and user_id = %s",
        (org["id"], org["owner"]),
    )
    assert role_of(db, org["id"], org["owner"]) == "admin"


def test_viewer_cannot_assign_roles(db, org):
    # Targeting a higher-ranked member is refused...
    db.act_as(org["viewer"])
    with pytest.raises(Exception, match="higher role"):
        db.execute(
            "update public.organization_members set role = 'admin' "
            "where organization_id = %s and user_id = %s",
            (org["id"], org["admin"]),
        )


def test_viewer_cannot_promote_a_peer_above_themselves(db, org):
    # ...and so is handing out a role above your own to a peer.
    peer = new_user(db, "peer@example.com")
    db.act_as(None)
    db.execute(
        "insert into public.organization_members "
        "(organization_id, user_id, role) values (%s, %s, 'viewer')",
        (org["id"], peer),
    )

    db.act_as(org["viewer"])
    with pytest.raises(Exception, match="cannot assign a role above your own"):
        db.execute(
            "update public.organization_members set role = 'admin' "
            "where organization_id = %s and user_id = %s",
            (org["id"], peer),
        )


# ----------------------------------------------------------------------
# The last owner
# ----------------------------------------------------------------------


def test_the_last_owner_cannot_be_demoted(db, org):
    db.act_as(None)  # even the service role may not break this invariant
    with pytest.raises(Exception, match="at least one owner"):
        db.execute(
            "update public.organization_members set role = 'admin' "
            "where organization_id = %s and user_id = %s",
            (org["id"], org["owner"]),
        )


def test_the_last_owner_cannot_be_deleted(db, org):
    db.act_as(None)
    with pytest.raises(Exception, match="at least one owner"):
        db.execute(
            "delete from public.organization_members "
            "where organization_id = %s and user_id = %s",
            (org["id"], org["owner"]),
        )


def test_the_last_owner_cannot_leave(db, org):
    db.act_as(org["owner"])
    with pytest.raises(Exception, match="at least one owner"):
        db.execute(
            "select public.leave_organization(%s)", (org["id"],)
        )


# ----------------------------------------------------------------------
# Removal & leaving
# ----------------------------------------------------------------------


def test_admin_can_remove_a_viewer(db, org):
    db.act_as(org["admin"])
    db.execute(
        "delete from public.organization_members "
        "where organization_id = %s and user_id = %s",
        (org["id"], org["viewer"]),
    )
    assert role_of(db, org["id"], org["viewer"]) is None


def test_viewer_cannot_remove_an_admin(db, org):
    db.act_as(org["viewer"])
    with pytest.raises(Exception, match="higher role"):
        db.execute(
            "delete from public.organization_members "
            "where organization_id = %s and user_id = %s",
            (org["id"], org["admin"]),
        )


def test_any_member_can_leave(db, org):
    db.act_as(org["viewer"])
    db.execute("select public.leave_organization(%s)", (org["id"],))
    assert role_of(db, org["id"], org["viewer"]) is None


# ----------------------------------------------------------------------
# Invitations
# ----------------------------------------------------------------------


def invite(db, organization_id, inviter, email, role="researcher"):
    db.act_as(inviter)
    return db.fetchone(
        "insert into public.organization_invitations "
        "(organization_id, email, role, invited_by) "
        "values (%s, %s, %s, %s) returning token",
        (organization_id, email, role, inviter),
    )[0]


def test_invitation_email_is_normalized(db, org):
    invite(db, org["id"], org["admin"], "  MiXeD@Example.COM  ")
    stored = db.fetchone(
        "select email from public.organization_invitations "
        "where organization_id = %s",
        (org["id"],),
    )[0]
    assert stored == "mixed@example.com"


def test_only_one_pending_invitation_per_email(db, org):
    invite(db, org["id"], org["admin"], "dup@example.com")
    with pytest.raises(Exception):
        invite(db, org["id"], org["admin"], "dup@example.com")


def test_accepting_an_invitation_creates_the_membership(db, org):
    token = invite(db, org["id"], org["admin"], "new@example.com", "researcher")

    invitee = new_user(db, "new@example.com")
    db.act_as(invitee, email="new@example.com")
    db.execute("select public.accept_invitation(%s)", (token,))

    assert role_of(db, org["id"], invitee) == "researcher"

    db.act_as(None)
    status = db.fetchone(
        "select status from public.organization_invitations where token = %s",
        (token,),
    )[0]
    assert status == "accepted"


def test_an_invitation_cannot_be_accepted_by_a_different_email(db, org):
    token = invite(db, org["id"], org["admin"], "intended@example.com")

    intruder = new_user(db, "intruder@example.com")
    db.act_as(intruder, email="intruder@example.com")

    with pytest.raises(Exception, match="different email address"):
        db.execute("select public.accept_invitation(%s)", (token,))

    assert role_of(db, org["id"], intruder) is None


def test_an_invitation_cannot_be_reused(db, org):
    token = invite(db, org["id"], org["admin"], "once@example.com")
    invitee = new_user(db, "once@example.com")

    db.act_as(invitee, email="once@example.com")
    db.execute("select public.accept_invitation(%s)", (token,))

    with pytest.raises(Exception, match="already been used"):
        db.execute("select public.accept_invitation(%s)", (token,))


def test_an_expired_invitation_is_refused(db, org):
    token = invite(db, org["id"], org["admin"], "late@example.com")

    db.act_as(None)
    db.execute(
        "update public.organization_invitations "
        "set expires_at = now() - interval '1 day' where token = %s",
        (token,),
    )

    invitee = new_user(db, "late@example.com")
    db.act_as(invitee, email="late@example.com")

    with pytest.raises(Exception, match="expired"):
        db.execute("select public.accept_invitation(%s)", (token,))


def test_a_revoked_invitation_is_refused(db, org):
    token = invite(db, org["id"], org["admin"], "nope@example.com")

    db.act_as(None)
    db.execute(
        "update public.organization_invitations set status = 'revoked' "
        "where token = %s",
        (token,),
    )

    invitee = new_user(db, "nope@example.com")
    db.act_as(invitee, email="nope@example.com")

    with pytest.raises(Exception, match="already been used or revoked"):
        db.execute("select public.accept_invitation(%s)", (token,))


def test_an_unknown_token_is_refused(db, org):
    stranger = new_user(db, "stranger@example.com")
    db.act_as(stranger, email="stranger@example.com")

    with pytest.raises(Exception, match="not valid"):
        db.execute("select public.accept_invitation('does-not-exist')")


def test_invitation_preview_exposes_only_safe_fields(db, org):
    token = invite(db, org["id"], org["admin"], "peek@example.com", "viewer")

    invitee = new_user(db, "peek@example.com")
    db.act_as(invitee, email="peek@example.com")

    row = db.fetchone("select * from public.invitation_preview(%s)", (token,))

    organization_id, name, email, role, status, _expires = row
    assert organization_id == org["id"]
    assert name == "Acme"
    assert email == "peek@example.com"
    assert role == "viewer"
    assert status == "pending"


def test_invitation_preview_reports_expiry(db, org):
    token = invite(db, org["id"], org["admin"], "stale@example.com")

    db.act_as(None)
    db.execute(
        "update public.organization_invitations "
        "set expires_at = now() - interval '1 second' where token = %s",
        (token,),
    )

    assert db.fetchone(
        "select status from public.invitation_preview(%s)", (token,)
    )[0] == "expired"


def test_a_member_cannot_forge_a_membership_without_an_invitation(db, org):
    intruder = new_user(db, "forger@example.com")
    db.act_as(intruder, email="forger@example.com")

    with pytest.raises(Exception, match="cannot assign a role above your own"):
        db.execute(
            "insert into public.organization_members "
            "(organization_id, user_id, role) values (%s, %s, 'admin')",
            (org["id"], intruder),
        )
