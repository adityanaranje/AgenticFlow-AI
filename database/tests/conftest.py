"""Test harness that runs the real migrations on a throwaway PostgreSQL.

Supabase provides an ``auth`` schema plus the ``auth.uid()`` / ``auth.jwt()``
helpers. Those are stubbed here (backed by session settings) so the
migrations can run unmodified against a vanilla PostgreSQL instance.

Skips itself when ``pgserver`` / ``psycopg`` are unavailable.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

MIGRATIONS = (
    pathlib.Path(__file__).resolve().parents[1] / "migrations"
)

# Supabase compatibility shim: an `auth` schema, a users table, and the
# `auth.uid()` / `auth.jwt()` helpers driven by session settings so tests
# can impersonate a user.
AUTH_SHIM = """
-- The bundled test PostgreSQL has no pgcrypto, so provide the two
-- functions the migrations use. `gen_random_uuid` is built in on modern
-- PostgreSQL; `gen_random_bytes` is emulated for invitation tokens.
create or replace function public.gen_random_bytes(count integer)
returns bytea
language sql
volatile
as $shim$
    select string_agg(
        set_byte('\\x00'::bytea, 0, (random() * 255)::integer),
        ''
    )
    from generate_series(1, count);
$shim$;

create schema if not exists auth;

create table if not exists auth.users (
    id uuid primary key,
    email text,
    raw_user_meta_data jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create or replace function auth.uid()
returns uuid
language sql
stable
as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;

create or replace function auth.jwt()
returns jsonb
language sql
stable
as $$
    select jsonb_build_object(
        'sub',   nullif(current_setting('request.jwt.claim.sub', true), ''),
        'email', coalesce(current_setting('request.jwt.claim.email', true), '')
    );
$$;

-- Supabase creates these roles; the migrations grant/reference them.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'service_role') then
        create role service_role;
    end if;
end
$$;

-- Minimal `storage` schema so migration 010 can run.
create schema if not exists storage;

create table if not exists storage.buckets (
    id text primary key,
    name text,
    public boolean default false
);

create table if not exists storage.objects (
    id uuid primary key default gen_random_uuid(),
    bucket_id text,
    name text,
    owner uuid
);
"""

# Migrations required for organization/member behaviour. The document,
# research, report and evaluation migrations are included so the RLS
# migration (009) finds every table it references.
MIGRATION_ORDER = [
    "001_extensions.sql",
    "002_profiles.sql",
    "003_organizations.sql",
    "004_documents.sql",
    "005_docuemnt_chunks.sql",
    "006_research.sql",
    "007_reports.sql",
    "008_evaluations.sql",
    "009_rls.sql",
    "010_storage.sql",
    "011_indexes.sql",
    "012_researcher_role.sql",
    "013_document_ingestion.sql",
    "014_research_reports.sql",
    "015_member_management.sql",
    "016_invitation_requests.sql",
]


class Database:
    """Thin psycopg wrapper that can impersonate a Supabase user."""

    def __init__(self, connection):
        self.connection = connection
        self.connection.autocommit = True

    def act_as(self, user_id: str | None, email: str = "") -> None:
        """Impersonate a user (or the trusted service role when ``None``)."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                "select set_config('request.jwt.claim.sub', %s, false)",
                (str(user_id) if user_id else "",),
            )
            cursor.execute(
                "select set_config('request.jwt.claim.email', %s, false)",
                (email or "",),
            )

    def execute(self, sql: str, params: tuple = ()):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def fetchall(self, sql: str, params: tuple = ()):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()


@pytest.fixture(scope="session")
def postgres():
    """A throwaway PostgreSQL instance, torn down after the session."""
    with tempfile.TemporaryDirectory() as directory:
        server = pgserver.get_server(directory, cleanup_mode="delete")
        try:
            yield server.get_uri()
        finally:
            server.cleanup()


@pytest.fixture(scope="session")
def schema(postgres):
    """Apply the auth shim + every migration once per session."""
    with psycopg.connect(postgres, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(AUTH_SHIM)

            for name in MIGRATION_ORDER:
                if name == "001_extensions.sql":
                    continue  # pgcrypto is shimmed above
                path = MIGRATIONS / name
                if not path.exists():
                    pytest.skip(f"missing migration {name}")
                cursor.execute(path.read_text())

    return postgres


@pytest.fixture()
def db(schema):
    """A clean database handle: tenant tables are truncated per test."""
    with psycopg.connect(schema, autocommit=True) as connection:
        database = Database(connection)
        database.act_as(None)
        database.execute(
            "truncate public.organization_members, "
            "public.organization_invitations, public.organizations, "
            "auth.users restart identity cascade"
        )
        yield database
