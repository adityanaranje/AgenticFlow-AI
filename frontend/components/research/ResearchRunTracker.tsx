"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  CircleAlert,
  FileText,
  Loader2,
  RotateCw,
  Sparkles,
} from "lucide-react";

export type RunView = {
  id: string;
  question: string;
  status: string;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  graph_state: Record<string, unknown> | null;
};

const LABEL: Record<string, string> = {
  queued: "Queued — waiting for a worker",
  planning: "Planning sub-questions",
  retrieving: "Retrieving evidence",
  analyzing: "Analyzing evidence",
  checking_gaps: "Checking for gaps",
  synthesizing: "Synthesizing the report",
  validating: "Validating citations",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function ResearchRunTracker({
  organizationId,
  runId,
  initial,
}: {
  organizationId: string;
  runId: string;
  initial: RunView;
}) {
  const [run, setRun] = useState<RunView>(initial);
  const [reportId, setReportId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const { createClient } = await import("@/lib/supabase/client");
    const supabase = createClient();
    const { data, error } = await supabase
      .from("research_runs")
      .select("id, question, status, error, created_at, started_at, completed_at, graph_state")
      .eq("id", runId)
      .eq("organization_id", organizationId)
      .maybeSingle();
    if (!error && data) {
      setRun(data as RunView);
    }
  }, [organizationId, runId]);

  useEffect(() => {
    let t: ReturnType<typeof setInterval> | null = null;
    const active = () => !["completed", "failed", "cancelled"].includes(run.status);
    if (active()) {
      t = setInterval(() => void refresh(), 5000);
    }
    return () => {
      if (t) clearInterval(t);
    };
  }, [run.status, refresh]);

  useEffect(() => {
    if (run.status === "completed") {
      const discover = async () => {
        const { createClient } = await import("@/lib/supabase/client");
        const supabase = createClient();
        const { data } = await supabase
          .from("reports")
          .select("id")
          .eq("research_run_id", runId)
          .eq("organization_id", organizationId)
          .maybeSingle();
        if (data?.id) setReportId(data.id);
      };
      void discover();
    }
  }, [run.status, runId, organizationId]);

  const running = !["completed", "failed", "cancelled"].includes(run.status);
  const gs = run.graph_state ?? {};
  const counts = {
    retrieved: Number(gs.retrieved_count ?? 0),
    evidence: Number(gs.evidence_count ?? 0),
    citations: Number(gs.citations_count ?? 0),
  };

  return (
    <div className="space-y-6">
      {/* Status */}
      <section className="card p-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {running ? (
              <Loader2 className="h-6 w-6 animate-spin text-indigo-500" aria-hidden="true" />
            ) : run.status === "completed" ? (
              <CheckCircle2 className="h-6 w-6 text-emerald-500" aria-hidden="true" />
            ) : (
              <CircleAlert className="h-6 w-6 text-rose-500" aria-hidden="true" />
            )}
            <div>
              <p className="text-base font-semibold text-zinc-900 dark:text-white">
                {LABEL[run.status] ?? run.status}
              </p>
              <p className="text-xs text-zinc-400">
                {run.question}
              </p>
            </div>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold capitalize ${statusClass(run.status)}`}>
            {run.status.replace("_", " ")}
          </span>
        </div>

        {running && (
          <div className="mt-4 flex items-center gap-1.5 text-xs font-medium text-sky-600 dark:text-sky-400">
            <RotateCw className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            Updating automatically…
          </div>
        )}

        {run.status === "failed" && run.error && (
          <div
            role="alert"
            className="mt-4 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
          >
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{run.error}</span>
          </div>
        )}
      </section>

      {/* Metrics */}
      <section className="grid grid-cols-3 gap-4">
        {[
          ["Chunks retrieved", counts.retrieved],
          ["Evidence claims", counts.evidence],
          ["Valid citations", counts.citations],
        ].map(([label, value]) => (
          <div key={label as string} className="card p-5 text-center">
            <p className="text-2xl font-semibold text-zinc-900 dark:text-white">{value}</p>
            <p className="mt-1 text-xs font-medium uppercase tracking-wide text-zinc-400">{label}</p>
          </div>
        ))}
      </section>

      {/* Report CTA */}
      {run.status === "completed" && (
        <section className="card p-6">
          <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-900 dark:text-white">
            <FileText className="h-5 w-5 text-indigo-500" aria-hidden="true" /> Generated report
          </h2>
          {reportId ? (
            <Link href={`/organizations/${organizationId}/reports/${reportId}`} className="btn-primary mt-4">
              <Sparkles className="h-4 w-4" aria-hidden="true" /> View report
            </Link>
          ) : (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              Saving the report… check back in a moment.
            </p>
          )}
        </section>
      )}
    </div>
  );
}

function statusClass(status: string): string {
  const map: Record<string, string> = {
    queued: "bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-200",
    completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
    failed: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
    cancelled: "bg-zinc-200 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300",
  };
  return map[status] ?? "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300";
}
