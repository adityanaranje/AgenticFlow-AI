-- ============================================================
-- AgentFlow AI
-- Migration 007
-- Reports and report sources
-- ============================================================

create table if not exists public.reports (
    id uuid primary key default gen_random_uuid(),

    research_run_id uuid not null
        references public.research_runs(id)
        on delete cascade,

    organization_id uuid not null
        references public.organizations(id)
        on delete cascade,

    title text not null,

    content text not null,

    summary text,

    confidence numeric(5,4),

    created_at timestamptz not null default now(),

    updated_at timestamptz not null default now(),

    constraint reports_confidence_check
        check (
            confidence is null
            or (
                confidence >= 0
                and confidence <= 1
            )
        )
);


drop trigger if exists reports_set_updated_at
on public.reports;


create trigger reports_set_updated_at
before update on public.reports
for each row
execute function public.set_updated_at();


-- ============================================================
-- Report sources
-- ============================================================

create table if not exists public.report_sources (
    id uuid primary key default gen_random_uuid(),

    report_id uuid not null
        references public.reports(id)
        on delete cascade,

    source_type text not null,

    document_id uuid
        references public.documents(id)
        on delete set null,

    chunk_id uuid
        references public.document_chunks(id)
        on delete set null,

    url text,

    title text,

    citation text not null,

    metadata jsonb not null default '{}'::jsonb,

    created_at timestamptz not null default now(),

    constraint report_sources_type_check
        check (
            source_type in (
                'internal',
                'web'
            )
        )
);