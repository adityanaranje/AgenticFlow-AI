import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowLeft,
  Calendar,
  FileText,
  Hash,
  Layers,
  ShieldAlert,
} from "lucide-react";

import OrgHeader from "@/components/organizations/OrgHeader";
import {
  getUserOrganizations,
  requireOrganizationMembership,
} from "@/lib/organizations/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Document",
};

type ChunkRow = {
  id: string;
  chunk_index: number;
  content: string;
  page_number: number | null;
  section: string | null;
  metadata: Record<string, unknown>;
  vector_point_id: string | null;
};

const statusMeta: Record<string, { label: string; className: string }> = {
  pending: {
    label: "Pending",
    className:
      "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  },
  processing: {
    label: "Processing",
    className:
      "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  },
  completed: {
    label: "Completed",
    className:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  },
  failed: {
    label: "Failed",
    className: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
  },
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export default async function OrganizationDocumentDetailPage({
  params,
}: {
  params: Promise<{ organizationId: string; documentId: string }>;
}) {
  const { organizationId, documentId } = await params;

  // Enforce membership before any tenant data is read. A non-member never
  // receives the document or its chunks (requireOrganizationMembership
  // redirects them away first).
  const { organization } = await requireOrganizationMembership(organizationId);

  const [allMemberships, supabase] = await Promise.all([
    getUserOrganizations(),
    createClient(),
  ]);

  const { data: document } = await supabase
    .from("documents")
    .select("*")
    .eq("id", documentId)
    .eq("organization_id", organization.id)
    .maybeSingle();

  if (!document) {
    return (
      <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
        <OrgHeader
          organizations={allMemberships.map((m) => ({
            organization: m.organization,
            role: m.membership.role,
          }))}
          currentOrganizationId={organization.id}
        />
        <main className="mx-auto max-w-3xl px-6 py-16 text-center">
          <p className="text-sm font-medium text-rose-500">
            Document not found in this organization.
          </p>
          <Link
            href={`/organizations/${organization.id}/documents`}
            className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 dark:text-indigo-400"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to documents
          </Link>
        </main>
      </div>
    );
  }

  const meta = statusMeta[document.status] ?? statusMeta.pending;

  const { count: chunkCount } = await supabase
    .from("document_chunks")
    .select("id", { count: "exact", head: true })
    .eq("document_id", document.id)
    .eq("organization_id", organization.id);

  const { data: chunks } = await supabase
    .from("document_chunks")
    .select("id, chunk_index, content, page_number, section, metadata, vector_point_id")
    .eq("document_id", document.id)
    .eq("organization_id", organization.id)
    .order("chunk_index", { ascending: true })
    .limit(100);

  const failed = document.status === "failed";

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <OrgHeader
        organizations={allMemberships.map((m) => ({
          organization: m.organization,
          role: m.membership.role,
        }))}
        currentOrganizationId={organization.id}
      />

      <main className="mx-auto max-w-4xl space-y-8 px-6 py-10">
        <Link
          href={`/organizations/${organization.id}/documents`}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-500 transition hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to documents
        </Link>

        {/* Header */}
        <section className="card p-7">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
            <div className="flex items-start gap-4">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                <FileText className="h-6 w-6" aria-hidden="true" />
              </span>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
                    {document.filename}
                  </h1>
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${meta.className}`}
                  >
                    {meta.label}
                  </span>
                </div>
                <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                  {document.organization_id.slice(0, 8)} · {organization.name}
                </p>
              </div>
            </div>
          </div>

          <dl className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <dt className="flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-zinc-400">
                <Hash className="h-3 w-3" aria-hidden="true" /> Type
              </dt>
              <dd className="mt-1 text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                {document.file_type?.toUpperCase()}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-zinc-400">
                Size
              </dt>
              <dd className="mt-1 text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                {formatBytes(Number(document.file_size))}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-zinc-400">
                Pages
              </dt>
              <dd className="mt-1 text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                {document.page_count ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-zinc-400">
                <Calendar className="h-3 w-3" aria-hidden="true" /> Uploaded
              </dt>
              <dd className="mt-1 text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                {formatDate(document.created_at)}
              </dd>
            </div>
          </dl>
        </section>

        {/* Processing error */}
        {failed && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
          >
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <div>
              <p className="font-semibold">Processing failed</p>
              <p className="mt-1">
                {document.processing_error ||
                  "This document could not be processed."}
              </p>
            </div>
          </div>
        )}

        {/* Chunks */}
        <section>
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
            <Layers className="h-5 w-5 text-indigo-500" aria-hidden="true" />
            Chunks
            <span className="text-sm font-normal text-zinc-400">
              ({chunkCount ?? 0})
            </span>
          </h2>

          {(chunks ?? []).length === 0 ? (
            <div className="rounded-2xl border-2 border-dashed border-zinc-300 bg-white/60 px-6 py-12 text-center text-sm text-zinc-400 dark:border-zinc-700 dark:bg-zinc-900/40">
              {document.status === "completed"
                ? "No chunks were stored."
                : "Chunks will appear once processing completes."}
            </div>
          ) : (
            <ul className="space-y-3">
              {(chunks ?? []).map((chunk: ChunkRow) => (
                <li
                  key={chunk.id}
                  className="card p-5"
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded-full bg-zinc-100 px-2 py-0.5 font-mono font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-300">
                      Chunk {chunk.chunk_index}
                    </span>
                    {typeof chunk.page_number === "number" && (
                      <span className="rounded-full bg-indigo-100 px-2 py-0.5 font-medium text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300">
                        p.{chunk.page_number}
                      </span>
                    )}
                    {chunk.section && (
                      <span className="text-zinc-400">§ {chunk.section}</span>
                    )}
                    {chunk.vector_point_id && (
                      <span className="ml-auto text-zinc-300 dark:text-zinc-600">
                        embedded ✓
                      </span>
                    )}
                  </div>
                  <p className="line-clamp-4 whitespace-pre-wrap text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
                    {chunk.content}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
