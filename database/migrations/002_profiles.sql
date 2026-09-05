-- ============================================================
-- AgentFlow AI
-- Migration 002
-- Profiles
-- ============================================================

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,

    full_name text,
    avatar_url text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);


-- ------------------------------------------------------------
-- Updated-at trigger function
-- ------------------------------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;


drop trigger if exists profiles_set_updated_at
on public.profiles;


create trigger profiles_set_updated_at
before update on public.profiles
for each row
execute function public.set_updated_at();


-- ------------------------------------------------------------
-- Automatically create profile when user signs up
-- ------------------------------------------------------------

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (
        id,
        full_name,
        avatar_url
    )
    values (
        new.id,
        coalesce(
            new.raw_user_meta_data ->> 'full_name',
            new.raw_user_meta_data ->> 'name'
        ),
        new.raw_user_meta_data ->> 'avatar_url'
    )
    on conflict (id) do nothing;

    return new;
end;
$$;


drop trigger if exists on_auth_user_created
on auth.users;


create trigger on_auth_user_created
after insert on auth.users
for each row
execute function public.handle_new_user();