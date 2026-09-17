"""Executable tests for in-app invitation requests (migration 016).

Covers the "send a request, answer it from your dashboard" flow:

  * `my_pending_invitations()` shows a user only their *own* incoming
    requests, enriched with data they cannot read directly (organization
    name, inviter name) and never the secret token,
  * `respond_to_invitation(id, accept)` joins or declines, with the same
    email / expiry / single-use checks as the token path,
  * `search_invitable_users()` cannot be used to enumerate the user
    directory.

NOTE: these tests connect as the database owner, for whom RLS is bypassed,
so they verify the *trigger* and `security definer` functions rather than
the RLS policies. That is deliberate — it proves the invariants still hold
on the service-role path, where RLS offers no protection at all.

Run with::

    pytest database/tests
"""

from __future__ import annotations

import uuid

import pytest


def new_user(db, email: str, full_name: str | None = None) -> str:
    """Create an auth user (the 002 trigger creates their profile)."""
    user_id = str(uuid.uuid4())
    db.execute(
        "insert into auth.users (id, email, raw_user_meta_data) "
        "values (%s, %s, %s::jsonb)",
        (
            user_id,
            email,
            '{"full_name": "%s"}' % full_name if full_name else "{}",
        ),
    )
    return user_id


@pytest.fixture()
def org(db):
    owner = new_user(db, "owner@example.com", "Ada Owner")
    admin = new_user(db, "admin@example.com", "Bob Admin")
    viewer = new_user(db, "viewer@example.com", "Cleo Viewer")

    db.act_as(owner, email="owner@example.com")
    organization_id = db.fetchone(
        "select id from public.create_organization('Acme', 'acme')"
    )[0]

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


def send_request(db, organization_id, inviter, email, role="researcher"):
    """An admin sends an invitation request to an email address."""
    db.act_as(inviter, email="admin@example.com")
    return db.fetchone(
        "insert into public.organization_invitations "
        "(organization_id, email, role, invited_by) "
        "values (%s, %s, %s, %s) returning id",
        (organization_id, email, role, inviter),
    )[0]


def role_of(db, organization_id, user_id):
    row = db.fetchone(
        "select role from public.organization_members "
        "where organization_id = %s and user_id = %s",
        (organization_id, user_id),
    )
    return row[0] if row else None


# ----------------------------------------------------------------------
# The invitee's inbox
# ----------------------------------------------------------------------


def test_invitee_sees_the_request_with_org_and_inviter_names(db, org):
    invitee = new_user(db, "new@example.com", "Dana New")
    send_request(db, org["id"], org["admin"], "new@example.com", "researcher")

    db.act_as(invitee, email="new@example.com")
    rows = db.fetchall("select * from public.my_pending_invitations()")

    assert len(rows) == 1
    (_id, organization_id, name, slug, role, invited_by, _created, _expires) = rows[0]
    assert organization_id == org["id"]
    assert name == "Acme"
    assert slug == "acme"
    assert role == "researcher"
    # The invitee cannot read `organizations` or the inviter's profile
    # directly, so these must come from the security-definer function.
    assert invited_by == "Bob Admin"


def test_the_inbox_never_leaks_the_token(db, org):
    invitee = new_user(db, "new@example.com")
    send_request(db, org["id"], org["admin"], "new@example.com")

    db.act_as(invitee, email="new@example.com")
    columns = db.fetchall(
        "select column_name from information_schema.columns "
        "where table_name = 'my_pending_invitations'"
    )
    # It is a function, not a table/view: assert on the returned row shape.
    assert columns == []

    row = db.fetchone("select * from public.my_pending_invitations()")
    assert len(row) == 8  # id, org id, name, slug, role, inviter, created, expires


def test_a_user_cannot_see_somebody_elses_requests(db, org):
    new_user(db, "intended@example.com")
    send_request(db, org["id"], org["admin"], "intended@example.com")

    intruder = new_user(db, "intruder@example.com")
    db.act_as(intruder, email="intruder@example.com")

    assert db.fetchall("select * from public.my_pending_invitations()") == []


def test_expired_requests_are_hidden(db, org):
    invitee = new_user(db, "late@example.com")
    invitation_id = send_request(db, org["id"], org["admin"], "late@example.com")

    db.act_as(None)
    db.execute(
        "update public.organization_invitations "
        "set expires_at = now() - interval '1 day' where id = %s",
        (invitation_id,),
    )

    db.act_as(invitee, email="late@example.com")
    assert db.fetchall("select * from public.my_pending_invitations()") == []


def test_requests_for_organizations_you_already_joined_are_hidden(db, org):
    # The viewer is already a member; a stray invitation must not show up.
    db.act_as(None)
    db.execute(
        "insert into public.organization_invitations "
        "(organization_id, email, role, invited_by) values (%s, %s, %s, %s)",
        (org["id"], "viewer@example.com", "researcher", org["admin"]),
    )

    db.act_as(org["viewer"], email="viewer@example.com")
    assert db.fetchall("select * from public.my_pending_invitations()") == []


# ----------------------------------------------------------------------
# Responding
# ----------------------------------------------------------------------


def test_accepting_a_request_joins_the_organization(db, org):
    invitee = new_user(db, "new@example.com")
    invitation_id = send_request(db, org["id"], org["admin"], "new@example.com")

    db.act_as(invitee, email="new@example.com")
    result = db.fetchone(
        "select public.respond_to_invitation(%s, true)", (invitation_id,)
    )[0]

    assert result == "accepted"
    assert role_of(db, org["id"], invitee) == "researcher"
    # It disappears from the inbox afterwards.
    assert db.fetchall("select * from public.my_pending_invitations()") == []


def test_declining_a_request_does_not_join(db, org):
    invitee = new_user(db, "nope@example.com")
    invitation_id = send_request(db, org["id"], org["admin"], "nope@example.com")

    db.act_as(invitee, email="nope@example.com")
    result = db.fetchone(
        "select public.respond_to_invitation(%s, false)", (invitation_id,)
    )[0]

    assert result == "declined"
    assert role_of(db, org["id"], invitee) is None

    db.act_as(None)
    assert db.fetchone(
        "select status from public.organization_invitations where id = %s",
        (invitation_id,),
    )[0] == "declined"


def test_a_request_cannot_be_answered_twice(db, org):
    invitee = new_user(db, "once@example.com")
    invitation_id = send_request(db, org["id"], org["admin"], "once@example.com")

    db.act_as(invitee, email="once@example.com")
    db.execute("select public.respond_to_invitation(%s, true)", (invitation_id,))

    with pytest.raises(Exception, match="already been answered"):
        db.execute("select public.respond_to_invitation(%s, false)", (invitation_id,))


def test_a_request_cannot_be_answered_by_a_different_user(db, org):
    new_user(db, "intended@example.com")
    invitation_id = send_request(db, org["id"], org["admin"], "intended@example.com")

    intruder = new_user(db, "intruder@example.com")
    db.act_as(intruder, email="intruder@example.com")

    with pytest.raises(Exception, match="different email address"):
        db.execute("select public.respond_to_invitation(%s, true)", (invitation_id,))

    assert role_of(db, org["id"], intruder) is None


def test_an_expired_request_cannot_be_accepted(db, org):
    invitee = new_user(db, "late@example.com")
    invitation_id = send_request(db, org["id"], org["admin"], "late@example.com")

    db.act_as(None)
    db.execute(
        "update public.organization_invitations "
        "set expires_at = now() - interval '1 day' where id = %s",
        (invitation_id,),
    )

    db.act_as(invitee, email="late@example.com")
    with pytest.raises(Exception, match="expired"):
        db.execute("select public.respond_to_invitation(%s, true)", (invitation_id,))


def test_a_revoked_request_cannot_be_accepted(db, org):
    invitee = new_user(db, "gone@example.com")
    invitation_id = send_request(db, org["id"], org["admin"], "gone@example.com")

    db.act_as(None)
    db.execute(
        "update public.organization_invitations set status = 'revoked' "
        "where id = %s",
        (invitation_id,),
    )

    db.act_as(invitee, email="gone@example.com")
    with pytest.raises(Exception, match="already been answered"):
        db.execute("select public.respond_to_invitation(%s, true)", (invitation_id,))


def test_someone_can_be_re_invited_after_declining(db, org):
    invitee = new_user(db, "again@example.com")
    first = send_request(db, org["id"], org["admin"], "again@example.com")

    db.act_as(invitee, email="again@example.com")
    db.execute("select public.respond_to_invitation(%s, false)", (first,))

    # The pending-only unique index leaves room for a fresh request.
    second = send_request(db, org["id"], org["admin"], "again@example.com", "viewer")

    db.act_as(invitee, email="again@example.com")
    assert db.fetchone(
        "select public.respond_to_invitation(%s, true)", (second,)
    )[0] == "accepted"
    assert role_of(db, org["id"], invitee) == "viewer"


def test_an_owner_invitation_from_a_non_owner_cannot_be_accepted(db, org):
    """Defence in depth: even if an `owner` invitation is created out of
    band (bypassing RLS, e.g. via the service role), joining through it is
    refused unless the inviter really is an owner."""
    invitee = new_user(db, "sneaky@example.com")

    db.act_as(None)  # service role bypasses the RLS insert policy
    invitation_id = db.fetchone(
        "insert into public.organization_invitations "
        "(organization_id, email, role, invited_by) "
        "values (%s, 'sneaky@example.com', 'owner', %s) returning id",
        (org["id"], org["admin"]),  # invited_by is an admin, not an owner
    )[0]

    db.act_as(invitee, email="sneaky@example.com")
    with pytest.raises(Exception, match="Only an owner may grant the owner role"):
        db.execute("select public.respond_to_invitation(%s, true)", (invitation_id,))

    assert role_of(db, org["id"], invitee) is None


def test_an_owner_invitation_from_an_owner_is_honoured(db, org):
    invitee = new_user(db, "legit@example.com")

    db.act_as(org["owner"], email="owner@example.com")
    invitation_id = db.fetchone(
        "insert into public.organization_invitations "
        "(organization_id, email, role, invited_by) "
        "values (%s, 'legit@example.com', 'owner', %s) returning id",
        (org["id"], org["owner"]),
    )[0]

    db.act_as(invitee, email="legit@example.com")
    db.execute("select public.respond_to_invitation(%s, true)", (invitation_id,))

    assert role_of(db, org["id"], invitee) == "owner"



# ----------------------------------------------------------------------
# Finding people to invite
# ----------------------------------------------------------------------


def test_admin_can_find_a_user_by_exact_email(db, org):
    new_user(db, "findme@example.com", "Find Me")

    db.act_as(org["admin"], email="admin@example.com")
    rows = db.fetchall(
        "select * from public.search_invitable_users(%s, %s)",
        (org["id"], "findme@example.com"),
    )

    assert len(rows) == 1
    assert rows[0][1] == "Find Me"


def test_search_never_returns_email_addresses(db, org):
    new_user(db, "findme@example.com", "Find Me")

    db.act_as(org["admin"], email="admin@example.com")
    row = db.fetchone(
        "select * from public.search_invitable_users(%s, %s)",
        (org["id"], "findme@example.com"),
    )

    # (user_id, full_name, avatar_url, is_member) — no email column.
    assert len(row) == 4
    assert "findme@example.com" not in [str(value) for value in row]


def test_search_flags_existing_members(db, org):
    db.act_as(org["admin"], email="admin@example.com")
    row = db.fetchone(
        "select * from public.search_invitable_users(%s, %s)",
        (org["id"], "viewer@example.com"),
    )

    assert row[3] is True  # is_member


def test_search_rejects_partial_email_fishing(db, org):
    new_user(db, "secret@example.com", "Secret Person")

    db.act_as(org["admin"], email="admin@example.com")
    # A partial email is not an exact match and is not a name prefix.
    assert db.fetchall(
        "select * from public.search_invitable_users(%s, %s)",
        (org["id"], "secret@exam"),
    ) == []


def test_search_requires_at_least_three_characters(db, org):
    new_user(db, "ab@example.com", "Ab")

    db.act_as(org["admin"], email="admin@example.com")
    assert db.fetchall(
        "select * from public.search_invitable_users(%s, %s)", (org["id"], "Ab")
    ) == []


def test_non_admins_cannot_search_at_all(db, org):
    new_user(db, "findme@example.com", "Find Me")

    db.act_as(org["viewer"], email="viewer@example.com")
    assert db.fetchall(
        "select * from public.search_invitable_users(%s, %s)",
        (org["id"], "findme@example.com"),
    ) == []


def test_outsiders_cannot_search_another_organization(db, org):
    new_user(db, "findme@example.com", "Find Me")
    outsider = new_user(db, "outsider@example.com", "Out Sider")

    db.act_as(outsider, email="outsider@example.com")
    assert db.fetchall(
        "select * from public.search_invitable_users(%s, %s)",
        (org["id"], "findme@example.com"),
    ) == []


def test_resolve_invitable_email_requires_admin(db, org):
    target = new_user(db, "target@example.com", "Target Person")

    db.act_as(org["admin"], email="admin@example.com")
    assert db.fetchone(
        "select public.resolve_invitable_email(%s, %s)", (org["id"], target)
    )[0] == "target@example.com"

    # A viewer (or an outsider) cannot turn a user id into an email.
    db.act_as(org["viewer"], email="viewer@example.com")
    assert db.fetchone(
        "select public.resolve_invitable_email(%s, %s)", (org["id"], target)
    )[0] is None

    outsider = new_user(db, "outsider2@example.com")
    db.act_as(outsider, email="outsider2@example.com")
    assert db.fetchone(
        "select public.resolve_invitable_email(%s, %s)", (org["id"], target)
    )[0] is None
