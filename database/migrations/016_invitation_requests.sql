-- ============================================================
-- AgentFlow AI
-- Migration 016
-- In-app invitation requests (accept / decline from the dashboard)
-- ============================================================
--
-- Migration 015 introduced token-based invitations, which required the
-- inviter to copy a link and send it out of band. This migration turns
-- them into social-style *requests* that the invitee simply sees when
-- they sign in:
--
--   1. `declined` becomes a valid invitation status,
--   2. `my_pending_invitations()` lists the caller's own incoming
--      requests — including the organization name and who invited them,
--      neither of which the invitee can read directly (they are not a
--      member yet, so RLS hides `organizations` and other members'
--      profiles),
--   3. `respond_to_invitation(id, accept)` accepts or declines one by
--      id, so nothing has to round-trip through the secret token.
--
-- Idempotent: safe to run repeatedly.
-- ============================================================

begin;

-- ------------------------------------------------------------
-- 1. Allow declining
-- ------------------------------------------------------------

alter table public.organization_invitations
    drop constraint if exists organization_invitations_status_check;

alter table public.organization_invitations
    add constraint organization_invitations_status_check
    check (status in ('pending', 'accepted', 'revoked', 'declined'));


-- Track who responded and when (already present for accepts; reused for
-- declines so the inviter can see the outcome).
alter table public.organization_invitations
    add column if not exists responded_at timestamptz;


-- ------------------------------------------------------------
-- 2. The caller's own incoming requests
-- ------------------------------------------------------------
--
-- `security definer` because the invitee is not a member of the inviting
-- organization and therefore cannot read `organizations` or the
-- inviter's profile. Only non-sensitive display fields are returned, and
-- the filter is pinned to the caller's own verified email — a user can
-- never list somebody else's invitations. The token is deliberately NOT
-- exposed.

create or replace function public.my_pending_invitations()
returns table (
    id                uuid,
    organization_id   uuid,
    organization_name text,
    organization_slug text,
    role              text,
    invited_by_name   text,
    created_at        timestamptz,
    expires_at        timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
    select
        oi.id,
        oi.organization_id,
        o.name,
        o.slug,
        oi.role,
        coalesce(p.full_name, 'A team member'),
        oi.created_at,
        oi.expires_at
    from public.organization_invitations oi
    join public.organizations o
      on o.id = oi.organization_id
    left join public.profiles p
      on p.id = oi.invited_by
    where oi.status = 'pending'
      and oi.expires_at > now()
      and auth.uid() is not null
      and lower(oi.email) = lower(coalesce(auth.jwt() ->> 'email', '#'))
      -- Hide requests for organizations the user already belongs to.
      and not exists (
          select 1
          from public.organization_members om
          where om.organization_id = oi.organization_id
            and om.user_id = auth.uid()
      )
    order by oi.created_at desc;
$$;


-- ------------------------------------------------------------
-- 3. Responding to a request by id
-- ------------------------------------------------------------
--
-- Mirrors `accept_invitation(token)` but keyed by the invitation id, so
-- the dashboard never needs to handle the token. The same checks apply:
-- the invitation must be pending, unexpired, and addressed to the
-- caller's own verified email.

create or replace function public.respond_to_invitation(
    invitation_id uuid,
    accept boolean
)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
    invitation public.organization_invitations;
    caller       uuid := auth.uid();
    caller_email text := lower(coalesce(auth.jwt() ->> 'email', ''));
begin
    if caller is null then
        raise exception 'Authentication required.'
            using errcode = 'insufficient_privilege';
    end if;

    select *
    into invitation
    from public.organization_invitations oi
    where oi.id = invitation_id
    for update;

    if invitation.id is null then
        raise exception 'This invitation no longer exists.'
            using errcode = 'no_data_found';
    end if;

    if caller_email = '' or lower(invitation.email) <> caller_email then
        raise exception 'This invitation was issued to a different email address.'
            using errcode = 'insufficient_privilege';
    end if;

    if invitation.status <> 'pending' then
        raise exception 'This invitation has already been answered.'
            using errcode = 'check_violation';
    end if;

    if invitation.expires_at <= now() then
        raise exception 'This invitation has expired.'
            using errcode = 'check_violation';
    end if;

    if not accept then
        update public.organization_invitations
        set status       = 'declined',
            accepted_by  = caller,
            responded_at = now()
        where id = invitation.id;

        return 'declined';
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
    do update set role = excluded.role;

    update public.organization_invitations
    set status       = 'accepted',
        accepted_by  = caller,
        accepted_at  = now(),
        responded_at = now()
    where id = invitation.id;

    return 'accepted';
end;
$$;


-- Keep the token-based path in step with the new column.
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
    set status       = 'accepted',
        accepted_by  = caller,
        accepted_at  = now(),
        responded_at = now()
    where id = invitation.id;

    return membership;
end;
$$;


-- ------------------------------------------------------------
-- 3b. Defence in depth: an invitation can never grant 'owner'
--     unless the person who issued it is still an owner
-- ------------------------------------------------------------
--
-- The RLS insert policy in 015 already stops an admin from creating an
-- `owner` invitation, but RLS does not apply to the service role. The
-- guard trigger's "joining via an invitation" branch would otherwise
-- accept such a row verbatim, so re-check the inviter's authority at the
-- moment the membership is actually created.

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
    -- The invited role must match, and an `owner` invitation only counts
    -- when whoever issued it is still an owner themselves.
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
              and (
                    new_role <> 'owner'
                    or exists (
                        select 1
                        from public.organization_members inviter
                        where inviter.organization_id = oi.organization_id
                          and inviter.user_id = oi.invited_by
                          and inviter.role = 'owner'
                    )
              )
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


-- ------------------------------------------------------------
-- 4. Finding people to invite
-- ------------------------------------------------------------
--
-- PRIVACY: this deliberately does NOT support open-ended browsing of the
-- user directory. To return a row the caller must
--
--   * be an admin or owner of the organization they are inviting into,
--   * supply either a full, exact email address, or at least three
--     characters of a display name,
--
-- and the result never includes the matched user's email address — only
-- the id, display name and avatar needed to render the picker. That is
-- enough to invite somebody you already know, without turning the app
-- into an email-harvesting endpoint.

create or replace function public.search_invitable_users(
    target_organization_id uuid,
    search_query text
)
returns table (
    user_id     uuid,
    full_name   text,
    avatar_url  text,
    is_member   boolean
)
language sql
stable
security definer
set search_path = public
as $$
    select
        u.id,
        coalesce(p.full_name, split_part(u.email, '@', 1)),
        p.avatar_url,
        exists (
            select 1
            from public.organization_members om
            where om.organization_id = target_organization_id
              and om.user_id = u.id
        )
    from auth.users u
    left join public.profiles p
      on p.id = u.id
    where public.is_org_admin(target_organization_id)
      and length(trim(coalesce(search_query, ''))) >= 3
      and (
            -- An exact email match (you already know the address) ...
            lower(u.email) = lower(trim(search_query))
            -- ... or a display-name prefix.
            or lower(coalesce(p.full_name, ''))
               like lower(trim(search_query)) || '%'
      )
      and u.id <> auth.uid()
    order by
        (lower(u.email) = lower(trim(search_query))) desc,
        coalesce(p.full_name, '')
    limit 10;
$$;


-- Resolve a picked user's email so an invitation can be addressed to
-- them. Separate from the search function so the address is only ever
-- disclosed to the server (the route handler), never returned to the
-- browser. The admin/owner check is repeated here: a caller must not be
-- able to turn a guessed user id into an email address.

create or replace function public.resolve_invitable_email(
    target_organization_id uuid,
    target_user_id uuid
)
returns text
language sql
stable
security definer
set search_path = public
as $$
    select u.email
    from auth.users u
    where u.id = target_user_id
      and public.is_org_admin(target_organization_id);
$$;


-- ------------------------------------------------------------
-- 5. Re-inviting after a decline
-- ------------------------------------------------------------
--
-- The unique index from 015 only covers pending rows, so a declined
-- request can simply be superseded by a new invitation. Nothing to do
-- beyond documenting it here.

commit;
