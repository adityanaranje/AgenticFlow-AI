"use client";

import { useCallback, useState } from "react";
import { BarChart3, Loader2, CheckCircle2 } from "lucide-react";

export default function EvaluateButton({
  organizationId,
  reportId,
}: {
  organizationId: string;
  reportId: string;
}) {
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const evaluate = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/organizations/${organizationId}/evaluations`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(session?.access_token
              ? { Authorization: `Bearer ${session.access_token}` }
              : {}),
          },
          body: JSON.stringify({ report_id: reportId }),
        },
      );

      if (!res.ok) {
        const payload = await res.json().catch(() => null);
        throw new Error(payload?.detail || `Evaluation failed (${res.status})`);
      }

      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setRunning(false);
    }
  }, [organizationId, reportId]);

  if (done) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-1.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
        Evaluation complete
      </span>
    );
  }

  return (
    <div className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={evaluate}
        disabled={running}
        className="btn-primary px-4 py-2 text-sm disabled:opacity-50"
      >
        {running ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Evaluating…
          </>
        ) : (
          <>
            <BarChart3 className="h-4 w-4" aria-hidden="true" />
            Evaluate report
          </>
        )}
      </button>
      {error && (
        <span className="text-xs text-rose-600 dark:text-rose-400">{error}</span>
      )}
    </div>
  );
}
