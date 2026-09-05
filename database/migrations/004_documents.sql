-- ============================================================
-- AgentFlow AI
-- Migration 004
-- Documents
-- ============================================================

create table if not exists public.documents (
    id uuid primary key default gen_random_uuid(),

    organization_id uuid not null
        references public.organizations(id)
        on delete cascade,

    uploaded_by uuid not null
        references auth.users(id)
        on delete restrict,

    filename text not null,

    storage_path text not null,

    file_type text not null,

    file_size bigint not null,

    checksum text not null,

    status text not null default 'uploaded',

    page_count integer,

    metadata jsonb not null default '{}'::jsonb,

    created_at timestamptz not null default now(),

    updated_at timestamptz not null default now(),

    constraint documents_status_check
        check (
            status in (
                'uploaded',
                'processing',
                'ready',
                'failed'
            )
        ),

    constraint documents_file_size_check
        check (file_size >= 0),

    constraint documents_page_count_check
        check (
            page_count is null
            or page_count >= 0
        )
);


drop trigger if exists documents_set_updated_at
on public.documents;


create trigger documents_set_updated_at
before update on public.documents
for each row
execute function public.set_updated_at();


-- Prevent accidental duplicate files inside
-- the same organization.

create unique index if not exists documents_org_checksum_idx
on public.documents (
    organization_id,
    checksum
);