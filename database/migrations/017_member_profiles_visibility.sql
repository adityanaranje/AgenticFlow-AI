-- ============================================================
-- AgentFlow AI
-- Migration 017
-- Let organization members see each other's profiles
-- ============================================================
--
-- BUG: after accepting an invitation the members list rendered empty (or
-- showed only the viewer themselves).
--
-- Migration 002 created `profiles` and migration 009 gave it a single
-- select policy, `profiles_select_own`:
--
--     using (id = auth.uid())
--
-- So a signed-in user can read exactly one profile row: their own. The
-- members list joins `organization_members -> profiles`, and PostgREST
-- renders an embedded resource the caller cannot read as null. Any UI
-- that keys off the embedded profile therefore drops every member except
-- the current user — the roster looked empty even though the membership
-- rows were there all along.
--
-- FIX: additionally allow reading the profile of anybody you share an
-- organization with. This is the minimum needed to render a roster.
--
-- Scope: `profiles` holds only `full_name` and `avatar_url` — no email,
-- no credentials. Visibility is limited to co-members of an organization
-- you already belong to (`is_org_member` is itself security definer and
-- pinned to `auth.uid()`), so this does not expose a global directory.
-- The own-row policy is kept so a user with no organization can still
-- read their own profile, and updates remain own-row only.
--
-- Idempotent: safe to run repeatedly.
-- ============================================================

begin;

-- ------------------------------------------------------------
-- Helper: do two users share an organization?
-- ------------------------------------------------------------
--
-- security definer so the lookup itself is not filtered by the RLS
-- policy we are about to define (which would recurse).

create or replace function public.shares_organization_with(
    target_user_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.organization_members mine
        join public.organization_members theirs
          on theirs.organization_id = mine.organization_id
        where mine.user_id = auth.uid()
          and theirs.user_id = target_user_id
    );
$$;


-- ------------------------------------------------------------
-- Policy: co-members may read each other's profile
-- ------------------------------------------------------------

drop policy if exists profiles_select_co_member
on public.profiles;

create policy profiles_select_co_member
on public.profiles
for select
to authenticated
using (
    id = auth.uid()
    or public.shares_organization_with(id)
);


-- `profiles_select_own` (migration 009) stays in place. PostgreSQL ORs
-- permissive policies together, so keeping it is harmless and preserves
-- own-profile access for users who belong to no organization yet.
--
-- NOTE: no INSERT/UPDATE/DELETE policy is added here. Writes remain
-- own-row only via `profiles_update_own`.

commit;
