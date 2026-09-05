-- ============================================================
-- AgentFlow AI
-- Migration 005
-- Document chunks
-- ============================================================

create table if not exists public.document_chunks (
    id uuid primary key default gen_random_uuid(),

    document_id uuid not null
        references public.documents(id)
        on delete cascade,

    organization_id uuid not null
        references public.organizations(id)
        on delete cascade,

    chunk_index integer not null,

    content text not null,

    page_number integer,

    section text,

    metadata jsonb not null default '{}'::jsonb,

    created_at timestamptz not null default now(),

    constraint document_chunks_index_check
        check (chunk_index >= 0),

    constraint document_chunks_page_check
        check (
            page_number is null
            or page_number >= 1
        ),

    constraint document_chunks_unique_index
        unique (document_id, chunk_index)
);