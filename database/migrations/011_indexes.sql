-- ============================================================
-- AgentFlow AI
-- Migration 011
-- Database indexes
-- ============================================================


-- ============================================================
-- Organization membership
-- ============================================================

create index if not exists organization_members_user_idx
on public.organization_members(user_id);

create index if not exists organization_members_org_idx
on public.organization_members(organization_id);


-- ============================================================
-- Documents
-- ============================================================

create index if not exists documents_organization_idx
on public.documents(organization_id);

create index if not exists documents_uploaded_by_idx
on public.documents(uploaded_by);

create index if not exists documents_status_idx
on public.documents(status);

create index if not exists documents_created_at_idx
on public.documents(created_at desc);


-- ============================================================
-- Document chunks
-- ============================================================

create index if not exists document_chunks_document_idx
on public.document_chunks(document_id);

create index if not exists document_chunks_organization_idx
on public.document_chunks(organization_id);


-- ============================================================
-- Research
-- ============================================================

create index if not exists research_runs_organization_idx
on public.research_runs(organization_id);

create index if not exists research_runs_user_idx
on public.research_runs(user_id);

create index if not exists research_runs_status_idx
on public.research_runs(status);

create index if not exists research_runs_created_at_idx
on public.research_runs(created_at desc);


-- ============================================================
-- Reports
-- ============================================================

create index if not exists reports_organization_idx
on public.reports(organization_id);

create index if not exists reports_research_run_idx
on public.reports(research_run_id);

create index if not exists reports_created_at_idx
on public.reports(created_at desc);


-- ============================================================
-- Report sources
-- ============================================================

create index if not exists report_sources_report_idx
on public.report_sources(report_id);

create index if not exists report_sources_document_idx
on public.report_sources(document_id);

create index if not exists report_sources_chunk_idx
on public.report_sources(chunk_id);


-- ============================================================
-- Evaluations
-- ============================================================

create index if not exists evaluation_runs_organization_idx
on public.evaluation_runs(organization_id);

create index if not exists evaluation_results_run_idx
on public.evaluation_results(evaluation_run_id);