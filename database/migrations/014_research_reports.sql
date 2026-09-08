-- ============================================================
-- AgentFlow AI
-- Migration 014
-- Research / reports / evaluation (Phase 5)
-- ============================================================
--
-- * research_runs: richer lifecycle statuses + config column
-- * reports: keep structured metadata via JSON on the report
-- * evaluation_runs: link evaluations to reports + a status
--
-- Idempotent. Run from the Supabase SQL editor.
-- ============================================================

begin;

-- ------------------------------------------------------------
-- research_runs
-- ------------------------------------------------------------

-- Widen the status set to the Phase-5 lifecycle.
alter table public.research_runs
    drop constraint if exists research_runs_status_check;

alter table public.research_runs
    add constraint research_runs_status_check
    check (
        status in (
            'queued',
            'planning',
            'retrieving',
            'analyzing',
            'checking_gaps',
            'synthesizing',
            'validating',
            'completed',
            'failed',
            'cancelled',
            'running',
            'pending',
            'awaiting_human'
        )
    );

-- Per-run configuration (e.g. max iterations, model, top_k).
alter table public.research_runs
    add column if not exists config jsonb not null default '{}'::jsonb;

alter table public.research_runs
    alter column graph_state set default '{}'::jsonb;

-- ------------------------------------------------------------
-- reports
-- ------------------------------------------------------------

-- 'title' is required by the schema; keep it. Add a processed 'sections'
-- blob (executive_summary, findings, ...) derived at generation time.
alter table public.reports
    add column if not exists sections jsonb not null default '{}'::jsonb;

alter table public.reports
    add column if not exists status text not null default 'ready';

alter table public.reports
    add constraint reports_status_check
    check (status in ('generating', 'ready', 'failed'));

-- ------------------------------------------------------------
-- evaluation_runs
-- ------------------------------------------------------------

-- Link an evaluation to the report (and thus organization) it assesses.
alter table public.evaluation_runs
    add column if not exists report_id uuid
        references public.reports(id) on delete cascade;

alter table public.evaluation_runs
    add column if not exists status text not null default 'running';

alter table public.evaluation_runs
    add constraint evaluation_runs_status_check
    check (status in ('running', 'completed', 'failed'));

alter table public.evaluation_runs
    alter column dataset set default 'report-evaluation';

commit;
