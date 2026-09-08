-- ============================================================
-- AgentFlow AI
-- Migration 013
-- Document ingestion / RAG foundation
-- ============================================================
--
-- Phase 4 standardizes document lifecycle statuses on
--   pending | processing | completed | failed
-- (the Phase-2 schema used uploaded/processing/ready/failed), adds a
-- processing-error column for safe error surfacing, and links every
-- processed chunk row to its Qdrant vector point.
--
-- Idempotent. Safe to run from the Supabase SQL editor.
-- ============================================================

begin;

-- ------------------------------------------------------------
-- 1. Documents: standardize status values + add error column
-- ------------------------------------------------------------

alter table public.documents
    drop constraint if exists documents_status_check;

update public.documents
set status = 'pending'
where status = 'uploaded';

update public.documents
set status = 'completed'
where status = 'ready';

alter table public.documents
    alter column status set default 'pending';

alter table public.documents
    add constraint documents_status_check
    check (status in ('pending', 'processing', 'completed', 'failed'));

-- Sanitized, human-readable error message (never raw stack traces).
alter table public.documents
    add column if not exists processing_error text;

-- ------------------------------------------------------------
-- 2. Document chunks: link each row to its Qdrant vector point
-- ------------------------------------------------------------

alter table public.document_chunks
    add column if not exists vector_point_id uuid;

create index if not exists document_chunks_vector_point_idx
on public.document_chunks(vector_point_id);

commit;
