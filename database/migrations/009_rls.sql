-- ============================================================
-- AgentFlow AI
-- Migration 009
-- Row Level Security
-- ============================================================


-- ============================================================
-- Helper: organization membership
-- ============================================================

create or replace function public.is_org_member(
    target_organization_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.organization_members om
        where om.organization_id = target_organization_id
          and om.user_id = auth.uid()
    );
$$;


-- ============================================================
-- Helper: organization role
-- ============================================================

create or replace function public.org_role(
    target_organization_id uuid
)
returns text
language sql
stable
security definer
set search_path = public
as $$
    select om.role
    from public.organization_members om
    where om.organization_id = target_organization_id
      and om.user_id = auth.uid()
    limit 1;
$$;


-- ============================================================
-- Helper: admin/owner
-- ============================================================

create or replace function public.is_org_admin(
    target_organization_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select public.org_role(target_organization_id)
        in ('owner', 'admin');
$$;


-- ============================================================
-- Profiles
-- ============================================================

alter table public.profiles enable row level security;


drop policy if exists profiles_select_own
on public.profiles;

create policy profiles_select_own
on public.profiles
for select
to authenticated
using (
    id = auth.uid()
);


drop policy if exists profiles_update_own
on public.profiles;

create policy profiles_update_own
on public.profiles
for update
to authenticated
using (
    id = auth.uid()
)
with check (
    id = auth.uid()
);


-- ============================================================
-- Organizations
-- ============================================================

alter table public.organizations enable row level security;


drop policy if exists organizations_select_member
on public.organizations;

create policy organizations_select_member
on public.organizations
for select
to authenticated
using (
    public.is_org_member(id)
);


drop policy if exists organizations_update_admin
on public.organizations;

create policy organizations_update_admin
on public.organizations
for update
to authenticated
using (
    public.is_org_admin(id)
)
with check (
    public.is_org_admin(id)
);


-- ============================================================
-- Organization members
-- ============================================================

alter table public.organization_members
enable row level security;


drop policy if exists organization_members_select_member
on public.organization_members;

create policy organization_members_select_member
on public.organization_members
for select
to authenticated
using (
    public.is_org_member(organization_id)
);


drop policy if exists organization_members_insert_admin
on public.organization_members;

create policy organization_members_insert_admin
on public.organization_members
for insert
to authenticated
with check (
    public.is_org_admin(organization_id)
);


drop policy if exists organization_members_update_admin
on public.organization_members;

create policy organization_members_update_admin
on public.organization_members
for update
to authenticated
using (
    public.is_org_admin(organization_id)
)
with check (
    public.is_org_admin(organization_id)
);


drop policy if exists organization_members_delete_admin
on public.organization_members;

create policy organization_members_delete_admin
on public.organization_members
for delete
to authenticated
using (
    public.is_org_admin(organization_id)
);


-- ============================================================
-- Documents
-- ============================================================

alter table public.documents enable row level security;


drop policy if exists documents_select_member
on public.documents;

create policy documents_select_member
on public.documents
for select
to authenticated
using (
    public.is_org_member(organization_id)
);


drop policy if exists documents_insert_analyst
on public.documents;

create policy documents_insert_analyst
on public.documents
for insert
to authenticated
with check (
    public.is_org_member(organization_id)
    and public.org_role(organization_id)
        in ('owner', 'admin', 'analyst')
    and uploaded_by = auth.uid()
);


drop policy if exists documents_update_analyst
on public.documents;

create policy documents_update_analyst
on public.documents
for update
to authenticated
using (
    public.is_org_member(organization_id)
    and public.org_role(organization_id)
        in ('owner', 'admin', 'analyst')
)
with check (
    public.is_org_member(organization_id)
);


drop policy if exists documents_delete_admin
on public.documents;

create policy documents_delete_admin
on public.documents
for delete
to authenticated
using (
    public.is_org_admin(organization_id)
);


-- ============================================================
-- Document chunks
-- ============================================================

alter table public.document_chunks enable row level security;


drop policy if exists document_chunks_select_member
on public.document_chunks;

create policy document_chunks_select_member
on public.document_chunks
for select
to authenticated
using (
    public.is_org_member(organization_id)
);


drop policy if exists document_chunks_insert_analyst
on public.document_chunks;

create policy document_chunks_insert_analyst
on public.document_chunks
for insert
to authenticated
with check (
    public.is_org_member(organization_id)
    and public.org_role(organization_id)
        in ('owner', 'admin', 'analyst')
);


drop policy if exists document_chunks_delete_admin
on public.document_chunks;

create policy document_chunks_delete_admin
on public.document_chunks
for delete
to authenticated
using (
    public.is_org_admin(organization_id)
);


-- ============================================================
-- Research runs
-- ============================================================

alter table public.research_runs enable row level security;


drop policy if exists research_runs_select_member
on public.research_runs;

create policy research_runs_select_member
on public.research_runs
for select
to authenticated
using (
    public.is_org_member(organization_id)
);


drop policy if exists research_runs_insert_member
on public.research_runs;

create policy research_runs_insert_member
on public.research_runs
for insert
to authenticated
with check (
    public.is_org_member(organization_id)
    and user_id = auth.uid()
);


drop policy if exists research_runs_update_member
on public.research_runs;

create policy research_runs_update_member
on public.research_runs
for update
to authenticated
using (
    public.is_org_member(organization_id)
)
with check (
    public.is_org_member(organization_id)
);


-- ============================================================
-- Reports
-- ============================================================

alter table public.reports enable row level security;


drop policy if exists reports_select_member
on public.reports;

create policy reports_select_member
on public.reports
for select
to authenticated
using (
    public.is_org_member(organization_id)
);


drop policy if exists reports_insert_member
on public.reports;

create policy reports_insert_member
on public.reports
for insert
to authenticated
with check (
    public.is_org_member(organization_id)
);


drop policy if exists reports_update_member
on public.reports;

create policy reports_update_member
on public.reports
for update
to authenticated
using (
    public.is_org_member(organization_id)
)
with check (
    public.is_org_member(organization_id)
);


drop policy if exists reports_delete_admin
on public.reports;

create policy reports_delete_admin
on public.reports
for delete
to authenticated
using (
    public.is_org_admin(organization_id)
);


-- ============================================================
-- Report sources
-- ============================================================

alter table public.report_sources enable row level security;


drop policy if exists report_sources_select_member
on public.report_sources;

create policy report_sources_select_member
on public.report_sources
for select
to authenticated
using (
    exists (
        select 1
        from public.reports r
        where r.id = report_sources.report_id
          and public.is_org_member(r.organization_id)
    )
);


drop policy if exists report_sources_insert_member
on public.report_sources;

create policy report_sources_insert_member
on public.report_sources
for insert
to authenticated
with check (
    exists (
        select 1
        from public.reports r
        where r.id = report_sources.report_id
          and public.is_org_member(r.organization_id)
    )
);


-- ============================================================
-- Evaluation runs
-- ============================================================

alter table public.evaluation_runs enable row level security;


drop policy if exists evaluation_runs_select_member
on public.evaluation_runs;

create policy evaluation_runs_select_member
on public.evaluation_runs
for select
to authenticated
using (
    public.is_org_member(organization_id)
);


drop policy if exists evaluation_runs_insert_analyst
on public.evaluation_runs;

create policy evaluation_runs_insert_analyst
on public.evaluation_runs
for insert
to authenticated
with check (
    public.is_org_member(organization_id)
    and public.org_role(organization_id)
        in ('owner', 'admin', 'analyst')
);


-- ============================================================
-- Evaluation results
-- ============================================================

alter table public.evaluation_results enable row level security;


drop policy if exists evaluation_results_select_member
on public.evaluation_results;

create policy evaluation_results_select_member
on public.evaluation_results
for select
to authenticated
using (
    exists (
        select 1
        from public.evaluation_runs er
        where er.id = evaluation_results.evaluation_run_id
          and public.is_org_member(er.organization_id)
    )
);


drop policy if exists evaluation_results_insert_analyst
on public.evaluation_results;

create policy evaluation_results_insert_analyst
on public.evaluation_results
for insert
to authenticated
with check (
    exists (
        select 1
        from public.evaluation_runs er
        where er.id = evaluation_results.evaluation_run_id
          and public.org_role(er.organization_id)
              in ('owner', 'admin', 'analyst')
    )
);