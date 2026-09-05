-- ============================================================
-- AgentFlow AI
-- Migration 010
-- Supabase Storage
-- ============================================================


-- ============================================================
-- Documents bucket
-- ============================================================

insert into storage.buckets (
    id,
    name,
    public
)
values (
    'documents',
    'documents',
    false
)
on conflict (id) do update
set public = false;


-- ============================================================
-- Storage RLS
-- ============================================================


-- ------------------------------------------------------------
-- Read documents
-- ------------------------------------------------------------

drop policy if exists documents_storage_select
on storage.objects;


create policy documents_storage_select
on storage.objects
for select
to authenticated
using (
    bucket_id = 'documents'
    and public.is_org_member(
        split_part(name, '/', 1)::uuid
    )
);


-- ------------------------------------------------------------
-- Upload documents
-- ------------------------------------------------------------

drop policy if exists documents_storage_insert
on storage.objects;


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
        'analyst'
    )
);


-- ------------------------------------------------------------
-- Update documents
-- ------------------------------------------------------------

drop policy if exists documents_storage_update
on storage.objects;


create policy documents_storage_update
on storage.objects
for update
to authenticated
using (
    bucket_id = 'documents'
    and public.is_org_member(
        split_part(name, '/', 1)::uuid
    )
)
with check (
    bucket_id = 'documents'
    and public.is_org_member(
        split_part(name, '/', 1)::uuid
    )
);


-- ------------------------------------------------------------
-- Delete documents
-- ------------------------------------------------------------

drop policy if exists documents_storage_delete
on storage.objects;


create policy documents_storage_delete
on storage.objects
for delete
to authenticated
using (
    bucket_id = 'documents'
    and public.org_role(
        split_part(name, '/', 1)::uuid
    ) in (
        'owner',
        'admin'
    )
);