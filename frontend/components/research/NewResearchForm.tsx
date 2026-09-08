"use client";

import { useState, type SubmitEvent } from "react";
import { useRouter } from "next/navigation";
import { CircleAlert, Loader2, Play, Settings2 } from "lucide-react";

import { API_BASE_URL } from "@/lib/env";

/**
 * Start an agentic research run for the current organization. Submits to the
 * FastAPI backend (which enqueues a Redis job and returns immediately), then
 * navigates to the run's detail page.
 */
export default function NewResearchForm({
  organizationId,
  canResearch,
}: {
  organizationId: string;
  canResearch: boolean;
}) {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [showConfig, setShowConfig] = useState(false);
  const [topK, setTopK] = useState(5);
  const [maxIterations, setMaxIterations] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = question.trim();
    if (q.length < 3) {
      setError("Enter a research question (at least 3 characters).");
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();

      const response = await fetch(
        `${API_BASE_URL}/organizations/${organizationId}/research`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(session?.access_token
              ? { Authorization: `Bearer ${session.access_token}` }
              : {}),
          },
          body: JSON.stringify({
            query: q,
            config: { top_k: topK, max_iterations: maxIterations },
          }),
        },
      );
      const payload = (await response.json().catch(() => null)) as
        | { id?: string; error?: string; message?: string }
        | null;
      if (!response.ok) {
        setError(payload?.error ?? "Could not start research.");
        setSubmitting(false);
        return;
      }
      setQuestion("");
      router.push(`/organizations/${organizationId}/research/${payload?.id}`);
      router.refresh();
    } catch (err) {
      console.error("Start research failed:", err);
      setError("A network error occurred.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!canResearch) {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        You have <strong>viewer</strong> access. Only researcher+, admin and
        owner members can start research runs.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="research-q" className="label">
          Research question
        </label>
        <textarea
          id="research-q"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          maxLength={4000}
          placeholder="e.g. What are the major risks in our cloud migration?"
          className="input-field w-full resize-y"
        />
      </div>

      <button
        type="button"
        onClick={() => setShowConfig((v) => !v)}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
      >
        <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
        Research configuration
      </button>

      {showConfig && (
        <div className="grid grid-cols-2 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <label className="text-sm">
            <span className="label">Retrieval top-k</span>
            <input
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="input-field"
            />
          </label>
          <label className="text-sm">
            <span className="label">Max iterations</span>
            <input
              type="number"
              min={1}
              max={6}
              value={maxIterations}
              onChange={(e) => setMaxIterations(Number(e.target.value))}
              className="input-field"
            />
          </label>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="btn-primary btn-block"
      >
        {submitting ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Starting research…
          </>
        ) : (
          <>
            <Play className="h-4 w-4" aria-hidden="true" />
            Start research
          </>
        )}
      </button>
    </form>
  );
}
