"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  CircleAlert,
  FileText,
  Loader2,
  RefreshCw,
  RotateCw,
} from "lucide-react";

import UploadDocumentForm from "@/components/documents/UploadDocumentForm";

export type DocumentRow = {
  id: string;
  organization_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: string;
  processing_error: string | null;
  page_count: number | null;
  created_at: string;
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

export default function OrganizationDocuments({
  organizationId,
  initialDocuments,
  canUpload = true,
}: {
  organizationId: string;
  initialDocuments: DocumentRow[];
  canUpload?: boolean;
}) {
  const [documents, setDocuments] = useState<DocumentRow[]>(initialDocuments);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const { data, error: err } = await supabase
        .from("documents")
        .select("*")
        .eq("organization_id", organizationId)
        .order("created_at", { ascending: false });
      if (err) {
        setError(err.message);
        return;
      }
      setError(null);
      setDocuments((data ?? []) as DocumentRow[]);
    } catch (e) {
      console.error("Refresh documents failed:", e);
    }
  }, [organizationId]);

  const poll = useCallback(async () => {
    // RLS restricts reads to the current org members.
    await refresh();
  }, [refresh]);

  useEffect(() => {
    // Poll until nothing is processing, then back off. Simple interval keeps
    // statuses fresh without manual refresh.
    timer.current = setInterval(() => {
      void poll();
    }, 5000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [poll]);

  const hasActive = documents.some((d) =>
    ["pending", "processing"].includes(d.status),
  );

  return (
    <div className="space-y-6">
      {canUpload && (
        <div className="card p-6">
          <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
            Upload a document
          </h2>
          <div className="mt-4">
            <UploadDocumentForm
              organizationId={organizationId}
              onUploaded={() => void refresh()}
            />
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
          Documents
          <span className="ml-2 text-sm font-normal text-zinc-400">
            ({documents.length})
          </span>
        </h2>
        <div className="flex items-center gap-3">
          {hasActive && (
            <span className="flex items-center gap-1.5 text-xs font-medium text-sky-600 dark:text-sky-400">
              <RotateCw className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Processing…
            </span>
          )}
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              void refresh().finally(() => setLoading(false));
            }}
            disabled={loading}
            className="btn-secondary rounded-full px-3 py-1.5 text-xs"
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {documents.length === 0 ? (
        <div className="rounded-3xl border-2 border-dashed border-zinc-300 bg-white/60 px-6 py-14 text-center dark:border-zinc-700 dark:bg-zinc-900/40">
          <FileText className="mx-auto h-8 w-8 text-zinc-300 dark:text-zinc-600" />
          <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
            No documents yet. Upload a PDF, TXT, Markdown or DOCX to build your
            knowledge base.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-zinc-100 overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
          {documents.map((doc) => {
            const meta = statusMeta[doc.status] ?? statusMeta.pending;
            return (
              <li key={doc.id}>
                <Link
                  href={`/organizations/${organizationId}/documents/${doc.id}`}
                  className="flex items-center justify-between gap-3 px-5 py-4 transition hover:bg-zinc-50 dark:hover:bg-zinc-800/60"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                      <FileText className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-zinc-900 dark:text-white">
                        {doc.filename}
                      </p>
                      <p className="text-xs text-zinc-400">
                        {doc.file_type.toUpperCase()} ·{" "}
                        {formatBytes(doc.file_size)} · uploaded{" "}
                        {formatDate(doc.created_at)}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${meta.className}`}
                  >
                    {meta.label}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
