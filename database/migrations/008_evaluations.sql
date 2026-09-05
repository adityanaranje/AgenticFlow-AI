-- ============================================================
-- AgentFlow AI
-- Migration 008
-- Evaluation runs and results
-- ============================================================

create table if not exists public.evaluation_runs (
    id uuid primary key default gen_random_uuid(),

    organization_id uuid not null
        references public.organizations(id)
        on delete cascade,

    type text not null,

    dataset text not null,

    started_at timestamptz,

    completed_at timestamptz,

    summary jsonb not null default '{}'::jsonb,

    created_at timestamptz not null default now()
);


create table if not exists public.evaluation_results (
    id uuid primary key default gen_random_uuid(),

    evaluation_run_id uuid not null
        references public.evaluation_runs(id)
        on delete cascade,

    test_case text not null,

    metric text not null,

    score numeric(10,6),

    expected jsonb,

    actual jsonb,

    metadata jsonb not null default '{}'::jsonb,

    created_at timestamptz not null default now(),

    constraint evaluation_results_score_check
        check (
            score is null
            or (
                score >= 0
                and score <= 1
            )
        )
);