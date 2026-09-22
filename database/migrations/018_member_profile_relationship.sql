-- ============================================================
-- AgentFlow AI
-- Migration 018
-- Give PostgREST a relationship to embed profiles from members
-- ============================================================
--
-- BUG: the members roster rendered "No members yet" even for the owner,
-- who is always present and can always read their own profile. So this
-- was never only an RLS problem (see 017) — the query itself was failing.
--
-- CAUSE: `organization_members.user_id` references `auth.users(id)`
-- (migration 003). There is no foreign key from `organization_members`
-- to `public.profiles`, and PostgREST resolves embedded resources
--
--     .select("user_id, role, profiles ( full_name )")
--
-- strictly through foreign keys. With no FK to follow, PostgREST cannot
-- build the embed and rejects the whole request (PGRST200). The frontend
-- discarded the error and rendered the resulting null data as an empty
-- roster — which is why it silently showed nobody rather than an error.
--
-- FIX: add a real foreign key `organization_members.user_id ->
-- profiles.id`. That is sound because `profiles.id` is itself the
-- primary key referencing `auth.users(id)` (migration 002), and a
-- profile row is created for every user by the `on_auth_user_created`
-- trigger. The existing FK to `auth.users` is kept: both constraints
-- describe the same truth, and dropping it would weaken referential
-- integrity against the auth table.
--
-- Backfills any missing profile rows first, so adding the constraint
-- cannot fail on pre-existing data (e.g. users created before the 002
-- trigger existed, or inserted directly by an admin).
--
-- Idempotent: safe to run repeatedly.
-- ============================================================

begin;

-- ------------------------------------------------------------
-- 1. Backfill profiles for any user that lacks one
-- ------------------------------------------------------------

insert into public.profiles (id, full_name, avatar_url)
select
    u.id,
    coalesce(
        u.raw_user_meta_data ->> 'full_name',
        u.raw_user_meta_data ->> 'name',
        split_part(u.email, '@', 1)
    ),
    u.raw_user_meta_data ->> 'avatar_url'
from auth.users u
where not exists (
    select 1 from public.profiles p where p.id = u.id
)
on conflict (id) do nothing;


-- ------------------------------------------------------------
-- 2. Foreign key so PostgREST can embed profiles
-- ------------------------------------------------------------
--
-- Named explicitly: PostgREST uses the constraint to infer the
-- relationship, and an explicit name keeps the embed hint stable.

alter table public.organization_members
    drop constraint if exists organization_members_user_id_profile_fkey;

alter table public.organization_members
    add constraint organization_members_user_id_profile_fkey
    foreign key (user_id)
    references public.profiles(id)
    on delete cascade;


-- ------------------------------------------------------------
-- 3. Same treatment for invitation authorship
-- ------------------------------------------------------------
--
-- `my_pending_invitations` joins `invited_by -> profiles` inside a
-- security definer function, so it does not need this. But any future
-- PostgREST embed of the inviter would hit the identical problem, and
-- the backfill above makes the constraint safe to add now.

alter table public.organization_invitations
    drop constraint if exists organization_invitations_invited_by_profile_fkey;

alter table public.organization_invitations
    add constraint organization_invitations_invited_by_profile_fkey
    foreign key (invited_by)
    references public.profiles(id)
    on delete cascade;


commit;
