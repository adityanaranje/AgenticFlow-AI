-- ============================================================
-- AgentFlow AI
-- Migration 012
-- Standardize the mid-tier organization role on "researcher"
-- ============================================================
--
-- Phase 2 scaffolding named the mid-tier organization role "analyst"
-- (migrations 003 / 009 / 010). Phase 3 RBAC standardizes on
-- "researcher". This migration:
--
--   1. widens the role check constraint to allow 'researcher',
--   2. migrates any existing 'analyst' memberships to 'researcher',
--   3. rebuilds every RLS / storage policy that gated on 'analyst'
--      so it now gates on 'researcher'.
--
-- It is idempotent and safe to run repeatedly from the Supabase
-- SQL editor or the migrations runner.
--
-- NOTE: this does NOT drop RLS. Row Level Security remains enabled;
-- only the role literal used by the policies is updated.
-- ============================================================

begin;

-- ------------------------------------------------------------
-- 1. Role check constraint: owner | admin | researcher | viewer
-- ------------------------------------------------------------

alter table public.organization_members
    drop constraint if exists organization_members_role_check;

alter table public.organization_members
    add constraint organization_members_role_check
    check (role in ('owner', 'admin', 'researcher', 'viewer'));

-- ------------------------------------------------------------
-- 2. Migrate existing rows ('analyst' -> 'researcher')
-- ------------------------------------------------------------

update public.organization_members
set role = 'researcher'
where role = 'analyst';

-- ------------------------------------------------------------
-- 3. RLS: Documents
-- ------------------------------------------------------------

drop policy if exists documents_insert_analyst on public.documents;
drop policy if exists documents_insert_researcher on public.documents;

create policy documents_insert_researcher
on public.documents
for insert
to authenticated
with check (
    public.is_org_member(organization_id)
    and public.org_role(organization_id)
        in ('owner', 'admin', 'researcher')
    and uploaded_by = auth.uid()
);

drop policy if exists documents_update_analyst on public.documents;
drop policy if exists documents_update_researcher on public.documents;

create policy documents_update_researcher
on public.documents
for update
to authenticated
using (
    public.is_org_member(organization_id)
    and public.org_role(organization_id)
        in ('owner', 'admin', 'researcher')
)
with check (
    public.is_org_member(organization_id)
);

-- ------------------------------------------------------------
-- 4. RLS: Document chunks
-- ------------------------------------------------------------

drop policy if exists document_chunks_insert_analyst on public.document_chunks;
drop policy if exists document_chunks_insert_researcher on public.document_chunks;

create policy document_chunks_insert_researcher
on public.document_chunks
for insert
to authenticated
with check (
    public.is_org_member(organization_id)
    and public.org_role(organization_id)
        in ('owner', 'admin', 'researcher')
);

-- ------------------------------------------------------------
-- 5. RLS: Evaluation runs
-- ------------------------------------------------------------

drop policy if exists evaluation_runs_insert_analyst on public.evaluation_runs;
drop policy if exists evaluation_runs_insert_researcher on public.evaluation_runs;

create policy evaluation_runs_insert_researcher
on public.evaluation_runs
for insert
to authenticated
with check (
    public.is_org_member(organization_id)
    and public.org_role(organization_id)
        in ('owner', 'admin', 'researcher')
);

-- ------------------------------------------------------------
-- 6. RLS: Evaluation results
-- ------------------------------------------------------------

drop policy if exists evaluation_results_insert_analyst on public.evaluation_results;
drop policy if exists evaluation_results_insert_researcher on public.evaluation_results;

create policy evaluation_results_insert_researcher
on public.evaluation_results
for insert
to authenticated
with check (
    exists (
        select 1
        from public.evaluation_runs er
        where er.id = evaluation_results.evaluation_run_id
          and public.org_role(er.organization_id)
              in ('owner', 'admin', 'researcher')
    )
);

-- ------------------------------------------------------------
-- 7. Storage: upload documents
-- ------------------------------------------------------------

drop policy if exists documents_storage_insert on storage.objects;

create policy documents_storage_insert
on storage.objects
for insert
to authenticated
with check (
    bucket_id = 'documents'
    and public.org_role(
        split_part(name, '/', 1)::uuid
    ) in (
        'owner',
        'admin',
        'researcher'
    )
);

commit;
