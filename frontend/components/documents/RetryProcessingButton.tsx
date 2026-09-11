"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, RotateCcw } from "lucide-react";

import apiClient from "@/lib/api/client";

/**
 * Retry background processing for a FAILED document (or refresh metadata
 * of a completed one that predates a parser fix — e.g. a null page count).
 *
 * Calls the backend reprocess endpoint (researcher+ enforced server-side),
 * which resets the document to `pending` and re-enqueues the standard
 * ingestion pipeline. The page is refreshed so the new status shows up.
 */
export default function RetryProcessingButton({
  organizationId,
  documentId,
  label = "Retry processing",
}: {
  organizationId: string;
  documentId: string;
  label?: string;
}) {
  const router = useRouter();
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRetry() {
    setError(null);
    setRetrying(true);
    try {
      await apiClient.post(
        `/organizations/${organizationId}/documents/${documentId}/reprocess`,
      );
      router.refresh();
      // Keep the spinner until the refresh swaps the status UI in.
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not retry processing.",
      );
      setRetrying(false);
    }
  }

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={handleRetry}
        disabled={retrying}
        className="inline-flex items-center gap-2 rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {retrying ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
        )}
        {retrying ? "Retrying…" : label}
      </button>
      {error && <p className="mt-2 text-xs text-rose-600 dark:text-rose-300">{error}</p>}
    </div>
  );
}
