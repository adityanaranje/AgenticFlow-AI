"""Members must be able to see each other's profiles (migration 017).

Regression test for the bug where the members roster rendered empty after
someone accepted an invitation: `profiles` RLS only exposed the caller's
own row, so the `organization_members -> profiles` embed returned null for
everybody else and the UI dropped them.

Unlike the other files here, these tests run as the **`authenticated`**
role inside a single transaction, so the RLS policies are genuinely
exercised (the database owner bypasses RLS entirely).
"""

from __future__ import annotations

import uuid

import pytest
import psycopg


@pytest.fixture()
def rls(db, schema):
    """Grants + a helper that queries as a given signed-in user."""
    db.act_as(None)
    db.execute(
        """
        grant usage on schema public, auth to authenticated;
        grant select, insert, update, delete
            on all tables in schema public to authenticated;
        grant execute on all functions in schema public to authenticated;
        grant select on auth.users to authenticated;
        """
    )

    def as_user(user_id: str, sql: str, params: tuple = (), email: str = ""):
        # One transaction, like a PostgREST request: set_config(local) then
        # drop to the `authenticated` role so RLS actually applies.
        with psycopg.connect(schema) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select set_config('request.jwt.claim.sub', %s, true)",
                    (str(user_id),),
                )
                cursor.execute(
                    "select set_config('request.jwt.claim.email', %s, true)",
                    (email,),
                )
                cursor.execute("set local role authenticated")
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            connection.rollback()
        return rows

    return as_user


def make_user(db, email: str, full_name: str) -> str:
    user_id = str(uuid.uuid4())
    db.act_as(None)
    db.execute(
        "insert into auth.users (id, email, raw_user_meta_data) "
        'values (%s, %s, %s::jsonb)',
        (user_id, email, '{"full_name": "%s"}' % full_name),
    )
    return user_id


@pytest.fixture()
def team(db):
    """An org with an owner and a member who joined via invitation."""
    owner = make_user(db, "owner@example.com", "Ada Owner")
    joiner = make_user(db, "new@example.com", "Dana New")

    db.act_as(owner, email="owner@example.com")
    organization_id = db.fetchone(
        "select id from public.create_organization('Acme', 'acme')"
    )[0]

    db.act_as(None)
    db.execute(
        "insert into public.organization_members "
        "(organization_id, user_id, role) values (%s, %s, 'researcher')",
        (organization_id, joiner),
    )

    return {"id": organization_id, "owner": owner, "joiner": joiner}


ROSTER_SQL = """
    select om.user_id, p.full_name
    from public.organization_members om
    join public.profiles p on p.id = om.user_id
    where om.organization_id = %s
    order by p.full_name
"""


def test_roster_shows_every_member_not_just_yourself(rls, team):
    """The actual bug: the joined roster must not collapse to one row."""
    rows = rls(team["owner"], ROSTER_SQL, (team["id"],), "owner@example.com")

    names = [row[1] for row in rows]
    assert names == ["Ada Owner", "Dana New"], names


def test_the_new_member_also_sees_the_whole_roster(rls, team):
    rows = rls(team["joiner"], ROSTER_SQL, (team["id"],), "new@example.com")

    assert [row[1] for row in rows] == ["Ada Owner", "Dana New"]


def test_membership_rows_were_always_visible(rls, team):
    """Confirms the fault was the profiles embed, not the membership RLS."""
    rows = rls(
        team["owner"],
        "select user_id from public.organization_members "
        "where organization_id = %s",
        (team["id"],),
        "owner@example.com",
    )
    assert len(rows) == 2


def test_profiles_are_not_exposed_to_unrelated_users(rls, db, team):
    """Co-membership is the boundary — not a global user directory."""
    outsider = make_user(db, "outsider@example.com", "Otto Outsider")

    rows = rls(
        outsider,
        "select id, full_name from public.profiles order by full_name",
        (),
        "outsider@example.com",
    )

    # Only their own profile; neither Acme member leaks.
    assert [row[1] for row in rows] == ["Otto Outsider"]


def test_leaving_an_organization_revokes_profile_visibility(rls, db, team):
    rows = rls(team["joiner"], ROSTER_SQL, (team["id"],), "new@example.com")
    assert len(rows) == 2

    db.act_as(team["joiner"], email="new@example.com")
    db.execute("select public.leave_organization(%s)", (team["id"],))

    rows = rls(
        team["joiner"],
        "select id, full_name from public.profiles order by full_name",
        (),
        "new@example.com",
    )
    assert [row[1] for row in rows] == ["Dana New"]


def test_profiles_remain_read_only_for_other_users(rls, team):
    """Visibility must not imply write access."""
    rows = rls(
        team["joiner"],
        "update public.profiles set full_name = 'Hacked' "
        "where id = %s returning id",
        (team["owner"],),
        "new@example.com",
    )
    assert rows == []


def test_a_user_with_no_organization_still_sees_their_own_profile(rls, db):
    loner = make_user(db, "loner@example.com", "Lo Ner")

    rows = rls(
        loner,
        "select full_name from public.profiles",
        (),
        "loner@example.com",
    )
    assert [row[0] for row in rows] == ["Lo Ner"]


# ----------------------------------------------------------------------
# The PostgREST embed relationship (migration 018)
# ----------------------------------------------------------------------


def test_members_have_a_foreign_key_to_profiles(db):
    """The roster embed `profiles(...)` is resolved by PostgREST through a
    foreign key. `organization_members.user_id` only referenced
    `auth.users`, so the embed failed with PGRST200 and the whole query
    errored — the UI showed "No members yet" even to the owner."""
    rows = db.fetchall(
        """
        select con.conname
        from pg_constraint con
        join pg_class src on src.oid = con.conrelid
        join pg_class tgt on tgt.oid = con.confrelid
        join pg_namespace tns on tns.oid = tgt.relnamespace
        where con.contype = 'f'
          and src.relname = 'organization_members'
          and tgt.relname = 'profiles'
          and tns.nspname = 'public'
        """
    )
    assert rows, (
        "organization_members needs a FK to public.profiles or PostgREST "
        "cannot embed the member's profile"
    )


def test_every_auth_user_has_a_profile_row(db):
    """The FK above only holds if a profile exists for every user; the
    `on_auth_user_created` trigger plus the 018 backfill guarantee it."""
    user_id = make_user(db, "fresh@example.com", "Fresh User")

    assert db.fetchone(
        "select full_name from public.profiles where id = %s", (user_id,)
    )[0] == "Fresh User"


def test_roster_embed_returns_all_members(rls, team):
    """The LEFT join the embed compiles to must list everyone."""
    rows = rls(
        team["owner"],
        """
        select om.user_id, om.role, p.full_name
        from public.organization_members om
        left join public.profiles p on p.id = om.user_id
        where om.organization_id = %s
        order by om.created_at
        """,
        (team["id"],),
        "owner@example.com",
    )

    assert [(row[1], row[2]) for row in rows] == [
        ("owner", "Ada Owner"),
        ("researcher", "Dana New"),
    ]
