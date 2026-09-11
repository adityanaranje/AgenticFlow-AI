"use client";

import { useState, type ChangeEvent, type SubmitEvent } from "react";
import { CheckCircle2, CircleAlert, Loader2, UploadCloud } from "lucide-react";

import { API_BASE_URL } from "@/lib/env";

const ACCEPTED_EXTENSIONS = ".pdf,.txt,.md,.markdown,.docx";

/**
 * Upload form. Sends the file to the FastAPI backend (which stores bytes in
 * private Supabase Storage and enqueues background processing), carrying the
 * caller's Supabase access token for authentication + membership.
 */
export default function UploadDocumentForm({
  organizationId,
  onUploaded,
}: {
  organizationId: string;
  onUploaded?: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function handlePick(event: ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files?.[0] ?? null;
    setFile(picked);
    setError(null);
    setSuccess(null);
  }

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }

    // Capture the form before awaiting: React nullifies `event.currentTarget`
    // once the synthetic event finishes dispatch, so reading it after an
    // `await` throws `Cannot read properties of null`.
    const formEl = event.currentTarget;

    setError(null);
    setSuccess(null);
    setUploading(true);

    try {
      // Resolve the caller's access token from the browser session.
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();

      const form = new FormData();
      form.append("file", file);

      const response = await fetch(
        `${API_BASE_URL}/organizations/${organizationId}/documents/upload`,
        {
          method: "POST",
          headers: session?.access_token
            ? { Authorization: `Bearer ${session.access_token}` }
            : {},
          body: form,
        },
      );

      const payload = (await response.json().catch(() => null)) as
        | {
            document?: {
              id?: string;
              status?: string;
              processing_error?: string | null;
            };
            detail?: string | Array<{ msg?: string }>;
            error?: string;
            message?: string;
          }
        | null;

      if (!response.ok) {
        // FastAPI reports errors under `detail` (a string for HTTPException,
        // or a list of {msg} objects for request-validation errors).
        const detail =
          typeof payload?.detail === "string"
            ? payload.detail
            : Array.isArray(payload?.detail)
              ? payload.detail
                  .map((item) => item?.msg)
                  .filter(Boolean)
                  .join(" ")
              : undefined;
        setError(detail ?? payload?.error ?? "Upload failed. Please try again.");
        setUploading(false);
        return;
      }

      // The record may be stored but processing can fail inline (e.g. in a
      // dev setup without Redis, processing runs inside the request and its
      // outcome comes back on the document itself).
      if (payload?.document?.status === "failed") {
        onUploaded?.();
        setError(
          payload.document.processing_error ??
            `"${file.name}" was stored but processing failed. Check that the document worker, OpenAI and Qdrant are configured.`,
        );
        return;
      }

      setFile(null);
      // Reset the input value so the same file can be chosen again.
      const input = formEl.elements.namedItem(
        "file",
      ) as HTMLInputElement | null;
      if (input) input.value = "";
      setSuccess(
        payload?.message ??
          `"${file.name}" uploaded and processing has started.`,
      );
      onUploaded?.();
    } catch (err) {
      console.error("Upload error:", err);
      setError("A network error occurred during upload.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <label className="flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-zinc-300 bg-white/50 px-6 py-10 text-center transition hover:border-indigo-400 hover:bg-indigo-50/40 dark:border-zinc-700 dark:bg-zinc-900/40 dark:hover:border-indigo-500/60">
        <input
          id="document-upload"
          name="file"
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          onChange={handlePick}
          className="sr-only"
          required
        />
        <UploadCloud className="h-9 w-9 text-indigo-500" aria-hidden="true" />
        <span className="mt-3 text-sm font-semibold text-zinc-800 dark:text-zinc-100">
          {file ? file.name : "Choose a document to upload"}
        </span>
        <span className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          PDF, TXT, Markdown or DOCX · up to 25 MB
        </span>
      </label>

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-sm text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300"
        >
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{success}</span>
        </div>
      )}

      <button
        type="submit"
        disabled={uploading || !file}
        className="btn-primary btn-block"
      >
        {uploading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Uploading…
          </>
        ) : (
          <>
            <UploadCloud className="h-4 w-4" aria-hidden="true" />
            Upload document
          </>
        )}
      </button>
    </form>
  );
}
