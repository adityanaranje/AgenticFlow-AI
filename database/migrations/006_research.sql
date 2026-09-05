-- ============================================================
-- AgentFlow AI
-- Migration 006
-- Research runs
-- ============================================================

create table if not exists public.research_runs (
    id uuid primary key default gen_random_uuid(),

    organization_id uuid not null
        references public.organizations(id)
        on delete cascade,

    user_id uuid not null
        references auth.users(id)
        on delete restrict,

    question text not null,

    status text not null default 'pending',

    graph_state jsonb not null default '{}'::jsonb,

    started_at timestamptz,

    completed_at timestamptz,

    error text,

    created_at timestamptz not null default now(),

    constraint research_runs_status_check
        check (
            status in (
                'pending',
                'running',
                'awaiting_human',
                'completed',
                'failed'
            )
        )
);