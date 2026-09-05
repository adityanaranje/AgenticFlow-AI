-- ============================================================
-- AgentFlow AI
-- Migration 003
-- Organizations and membership
-- ============================================================


-- ============================================================
-- Organizations
-- ============================================================

create table if not exists public.organizations (
    id uuid primary key default gen_random_uuid(),

    name text not null,

    slug text not null unique,

    created_by uuid not null
        references auth.users(id)
        on delete restrict,

    created_at timestamptz not null default now(),

    updated_at timestamptz not null default now()
);


drop trigger if exists organizations_set_updated_at
on public.organizations;


create trigger organizations_set_updated_at
before update on public.organizations
for each row
execute function public.set_updated_at();


-- ============================================================
-- Organization members
-- ============================================================

create table if not exists public.organization_members (
    id uuid primary key default gen_random_uuid(),

    organization_id uuid not null
        references public.organizations(id)
        on delete cascade,

    user_id uuid not null
        references auth.users(id)
        on delete cascade,

    role text not null default 'viewer',

    created_at timestamptz not null default now(),

    updated_at timestamptz not null default now(),

    constraint organization_members_role_check
        check (role in (
            'owner',
            'admin',
            'analyst',
            'viewer'
        )),

    constraint organization_members_unique
        unique (organization_id, user_id)
);


drop trigger if exists organization_members_set_updated_at
on public.organization_members;


create trigger organization_members_set_updated_at
before update on public.organization_members
for each row
execute function public.set_updated_at();


-- ============================================================
-- Organization creation helper
-- ============================================================

create or replace function public.create_organization(
    organization_name text,
    organization_slug text
)
returns public.organizations
language plpgsql
security definer
set search_path = public
as $$
declare
    new_organization public.organizations;
begin

    insert into public.organizations (
        name,
        slug,
        created_by
    )
    values (
        organization_name,
        organization_slug,
        auth.uid()
    )
    returning *
    into new_organization;


    insert into public.organization_members (
        organization_id,
        user_id,
        role
    )
    values (
        new_organization.id,
        auth.uid(),
        'owner'
    );


    return new_organization;
end;
$$;