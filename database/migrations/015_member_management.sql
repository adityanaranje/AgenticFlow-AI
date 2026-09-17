-- ============================================================
-- AgentFlow AI
-- Migration 015
-- Organization member management + invitations
-- ============================================================
--
-- Migration 009 already lets an admin/owner insert, update and delete
-- rows in `organization_members`. That is too permissive on its own:
--
--   * an admin could promote themselves to 'owner',
--   * an admin could demote or delete the *last* owner, orphaning the
--     organization,
--   * an admin could remove an owner outright.
--
-- This migration closes those holes with database-level triggers (the
-- authoritative boundary) and adds a proper token-based invitation flow
-- so members can be invited by email before they have an account.
--
-- Idempotent: safe to run repeatedly.
-- ============================================================

begin;

-- ------------------------------------------------------------
-- 1. Guard trigger: protect the owner role
-- ------------------------------------------------------------
--
-- Rules enforced for any non-superuser statement against
-- `organization_members`:
--
--   a) granting or revoking 'owner' requires the actor to be an owner,
--   b) the last remaining owner can never be demoted or deleted,
--   c) an actor may never modify a member whose role outranks theirs,
--   d) an actor may not change their own role (prevents self-promotion
--      and accidental self-lockout); leaving voluntarily is handled by
--      `leave_organization` below.
--
-- `auth.uid()` is null for service-role / SQL-editor connections, which
-- are treated as trusted and bypass the actor checks (but never (b)).

create or replace function public.role_rank(target_role text)
returns integer
language sql
immutable
as $$
    select case target_role
        when 'owner'      then 4
        when 'admin'      then 3
        when 'researcher' then 2
        when 'viewer'     then 1
        else 0
    end;
$$;


create or replace function public.guard_organization_members()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    target_organization_id uuid;
    target_user_id uuid;
    old_role text;
    new_role text;
    actor_id   uuid := auth.uid();
    actor_role text;
    owner_count integer;
    caller_email text := lower(coalesce(auth.jwt() ->> 'email', ''));
    self_invited boolean := false;
begin
    -- PL/pgSQL does not guarantee short-circuit evaluation, and NEW is
    -- unassigned during DELETE (OLD during INSERT), so copy the fields we
    -- need into locals exactly once.
    if tg_op = 'DELETE' then
        target_organization_id := old.organization_id;
        target_user_id         := old.user_id;
        old_role               := old.role;
    elsif tg_op = 'INSERT' then
        target_organization_id := new.organization_id;
        target_user_id         := new.user_id;
        new_role               := new.role;
    else
        target_organization_id := new.organization_id;
        target_user_id         := old.user_id;
        old_role               := old.role;
        new_role               := new.role;
    end if;

    if actor_id is not null then
        select om.role
        into actor_role
        from public.organization_members om
        where om.organization_id = target_organization_id
          and om.user_id = actor_id;
    end if;

    actor_role := coalesce(actor_role, '');

    -- ---- The last owner is indestructible, in every context ------
    if old_role = 'owner' and coalesce(new_role, '') <> 'owner' then
        select count(*)
        into owner_count
        from public.organization_members om
        where om.organization_id = target_organization_id
          and om.role = 'owner';

        if owner_count <= 1 then
            raise exception
                'An organization must always have at least one owner.'
                using errcode = 'check_violation';
        end if;
    end if;

    -- Trusted server-side contexts (service role, migrations, and the
    -- `create_organization` definer running without a JWT) stop here.
    if actor_id is null then
        if tg_op = 'DELETE' then
            return old;
        end if;
        return new;
    end if;

    -- ---- Bootstrapping a brand-new organization ------------------
    -- `create_organization` inserts the creator as the first owner while
    -- they are not yet a member. Allowed only when the organization has
    -- no members at all, so it can never be used to join an existing one.
    if tg_op = 'INSERT' and target_user_id = actor_id then
        if not exists (
            select 1
            from public.organization_members om
            where om.organization_id = target_organization_id
        ) then
            return new;
        end if;
    end if;

    -- ---- Joining yourself through a valid invitation -------------
    if tg_op = 'INSERT' and target_user_id = actor_id then
        select exists (
            select 1
            from public.organization_invitations oi
            where oi.organization_id = target_organization_id
              and oi.status = 'pending'
              and oi.expires_at > now()
              and oi.role = new_role
              and caller_email <> ''
              and lower(oi.email) = caller_email
        )
        into self_invited;

        if self_invited then
            return new;
        end if;
    end if;

    -- ---- Leaving voluntarily is always allowed -------------------
    -- (the last-owner rule above still applies)
    if tg_op = 'DELETE' and target_user_id = actor_id then
        return old;
    end if;

    -- ---- Nobody edits their own role -----------------------------
    if tg_op = 'UPDATE' and target_user_id = actor_id then
        if new_role is distinct from old_role then
            raise exception 'You cannot change your own role.'
                using errcode = 'insufficient_privilege';
        end if;
    end if;

    -- ---- Only an owner may grant or revoke 'owner' ---------------
    if actor_role <> 'owner' then
        if new_role = 'owner' then
            raise exception 'Only an owner may grant the owner role.'
                using errcode = 'insufficient_privilege';
        end if;

        if old_role = 'owner' then
            raise exception 'Only an owner may modify another owner.'
                using errcode = 'insufficient_privilege';
        end if;
    end if;

    -- ---- Never act on somebody who outranks you ------------------
    if tg_op in ('UPDATE', 'DELETE') and target_user_id <> actor_id then
        if public.role_rank(old_role) > public.role_rank(actor_role) then
            raise exception 'You cannot modify a member with a higher role.'
                using errcode = 'insufficient_privilege';
        end if;
    end if;

    -- ---- Never assign a role above your own ----------------------
    if new_role is not null then
        if public.role_rank(new_role) > public.role_rank(actor_role) then
            raise exception 'You cannot assign a role above your own.'
                using errcode = 'insufficient_privilege';
        end if;
    end if;

    if tg_op = 'DELETE' then
        return old;
    end if;

    return new;
end;
$$;



drop trigger if exists organization_members_guard
on public.organization_members;

create trigger organization_members_guard
before insert or update or delete on public.organization_members
for each row
execute function public.guard_organization_members();


-- ------------------------------------------------------------
-- 2. Leaving an organization voluntarily
-- ------------------------------------------------------------
--
-- The RLS delete policy is admin-only, so a viewer/researcher cannot
-- remove their own row. This `security definer` function lets any
-- member leave, while the guard trigger still prevents the last owner
-- from walking out.

create or replace function public.leave_organization(
    target_organization_id uuid
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    caller uuid := auth.uid();
begin
    if caller is null then
        raise exception 'Authentication required.'
            using errcode = 'insufficient_privilege';
    end if;

    delete from public.organization_members om
    where om.organization_id = target_organization_id
      and om.user_id = caller;
end;
$$;


-- ------------------------------------------------------------
-- 3. Invitations
-- ------------------------------------------------------------

create table if not exists public.organization_invitations (
    id uuid primary key default gen_random_uuid(),

    organization_id uuid not null
        references public.organizations(id)
        on delete cascade,

    email text not null,

    role text not null default 'viewer',

    token text not null unique
        default encode(gen_random_bytes(32), 'hex'),

    status text not null default 'pending',

    invited_by uuid not null
        references auth.users(id)
        on delete cascade,

    accepted_by uuid
        references auth.users(id)
        on delete set null,

    accepted_at timestamptz,

    expires_at timestamptz not null
        default (now() + interval '14 days'),

    created_at timestamptz not null default now(),

    updated_at timestamptz not null default now(),

    constraint organization_invitations_role_check
        check (role in ('owner', 'admin', 'researcher', 'viewer')),

    constraint organization_invitations_status_check
        check (status in ('pending', 'accepted', 'revoked')),

    constraint organization_invitations_email_check
        check (position('@' in email) > 1)
);


-- One live invitation per (organization, email).
create unique index if not exists organization_invitations_pending_unique
on public.organization_invitations (organization_id, lower(email))
where status = 'pending';

create index if not exists organization_invitations_org_idx
on public.organization_invitations (organization_id, status);

create index if not exists organization_invitations_email_idx
on public.organization_invitations (lower(email))
where status = 'pending';


drop trigger if exists organization_invitations_set_updated_at
on public.organization_invitations;

create trigger organization_invitations_set_updated_at
before update on public.organization_invitations
for each row
execute function public.set_updated_at();


-- Normalize the email on write so lookups are always case-insensitive.
create or replace function public.normalize_invitation_email()
returns trigger
language plpgsql
as $$
begin
    new.email := lower(trim(new.email));
    return new;
end;
$$;

drop trigger if exists organization_invitations_normalize_email
on public.organization_invitations;

create trigger organization_invitations_normalize_email
before insert or update on public.organization_invitations
for each row
execute function public.normalize_invitation_email();


-- ------------------------------------------------------------
-- 4. Invitation RLS
-- ------------------------------------------------------------

alter table public.organization_invitations
enable row level security;


-- Members may see their organization's invitations; an invited user may
-- see the invitations addressed to their own email.
drop policy if exists organization_invitations_select
on public.organization_invitations;

create policy organization_invitations_select
on public.organization_invitations
for select
to authenticated
using (
    public.is_org_member(organization_id)
    or lower(email) = lower(coalesce(auth.jwt() ->> 'email', ''))
);


drop policy if exists organization_invitations_insert_admin
on public.organization_invitations;

create policy organization_invitations_insert_admin
on public.organization_invitations
for insert
to authenticated
with check (
    public.is_org_admin(organization_id)
    and invited_by = auth.uid()
    -- Only an owner may invite somebody straight to 'owner'.
    and (role <> 'owner' or public.org_role(organization_id) = 'owner')
);


drop policy if exists organization_invitations_update_admin
on public.organization_invitations;

create policy organization_invitations_update_admin
on public.organization_invitations
for update
to authenticated
using (
    public.is_org_admin(organization_id)
)
with check (
    public.is_org_admin(organization_id)
    and (role <> 'owner' or public.org_role(organization_id) = 'owner')
);


drop policy if exists organization_invitations_delete_admin
on public.organization_invitations;

create policy organization_invitations_delete_admin
on public.organization_invitations
for delete
to authenticated
using (
    public.is_org_admin(organization_id)
);


-- ------------------------------------------------------------
-- 5. Accepting an invitation
-- ------------------------------------------------------------
--
-- Runs `security definer` so the membership row is created for the
-- *authenticated caller* without granting the browser any insert rights
-- on `organization_members`. The invitation email must match the
-- caller's own verified email.

create or replace function public.accept_invitation(
    invitation_token text
)
returns public.organization_members
language plpgsql
security definer
set search_path = public
as $$
declare
    invitation public.organization_invitations;
    caller       uuid := auth.uid();
    caller_email text := lower(coalesce(auth.jwt() ->> 'email', ''));
    membership   public.organization_members;
begin
    if caller is null then
        raise exception 'Authentication required.'
            using errcode = 'insufficient_privilege';
    end if;

    select *
    into invitation
    from public.organization_invitations oi
    where oi.token = invitation_token
    for update;

    if invitation.id is null then
        raise exception 'This invitation link is not valid.'
            using errcode = 'no_data_found';
    end if;

    if invitation.status <> 'pending' then
        raise exception 'This invitation has already been used or revoked.'
            using errcode = 'check_violation';
    end if;

    if invitation.expires_at <= now() then
        raise exception 'This invitation has expired.'
            using errcode = 'check_violation';
    end if;

    if caller_email = '' or lower(invitation.email) <> caller_email then
        raise exception 'This invitation was issued to a different email address.'
            using errcode = 'insufficient_privilege';
    end if;

    insert into public.organization_members (
        organization_id,
        user_id,
        role
    )
    values (
        invitation.organization_id,
        caller,
        invitation.role
    )
    on conflict (organization_id, user_id)
    do update set role = excluded.role
    returning * into membership;

    update public.organization_invitations
    set status      = 'accepted',
        accepted_by = caller,
        accepted_at = now()
    where id = invitation.id;

    return membership;
end;
$$;


-- ------------------------------------------------------------
-- 6. Invitation lookup for the accept page (pre-membership)
-- ------------------------------------------------------------
--
-- A signed-in invitee is not yet a member, so they cannot read the
-- organization row. This returns only the safe, non-tenant fields.

create or replace function public.invitation_preview(
    invitation_token text
)
returns table (
    organization_id   uuid,
    organization_name text,
    email             text,
    role              text,
    status            text,
    expires_at        timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
    select
        oi.organization_id,
        o.name,
        oi.email,
        oi.role,
        case
            when oi.status = 'pending' and oi.expires_at <= now()
                then 'expired'
            else oi.status
        end,
        oi.expires_at
    from public.organization_invitations oi
    join public.organizations o
      on o.id = oi.organization_id
    where oi.token = invitation_token;
$$;


commit;
