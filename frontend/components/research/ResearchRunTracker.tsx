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

/* ------------------------------------------------------------------ */
/* Pipeline steps shown in the progress graph                         */
/* ------------------------------------------------------------------ */

const PIPELINE_STEPS = [
  { key: "queued", label: "Queued" },
  { key: "planning", label: "Planning" },
  { key: "retrieving", label: "Retrieving" },
  { key: "analyzing", label: "Analyzing" },
  { key: "checking_gaps", label: "Gap check" },
  { key: "synthesizing", label: "Synthesizing" },
  { key: "validating", label: "Validating" },
  { key: "completed", label: "Complete" },
] as const;

const FAILED_STATUSES = new Set(["failed", "cancelled"]);

function stepState(
  stepKey: string,
  currentStatus: string,
  graphState: Record<string, unknown> | null,
): "done" | "active" | "upcoming" | "failed" {
  const idx = PIPELINE_STEPS.findIndex((s) => s.key === stepKey);

  // Normal terminal status "completed" - everything is done
  if (currentStatus === "completed") {
    return "done";
  }

  // Non-pipeline terminal statuses ("failed" / "cancelled")
  if (FAILED_STATUSES.has(currentStatus)) {
    // Try to find the last active step from graph_state so we can show
    // which step failed and mark everything before it as done.
    const lastStep = (graphState?.last_step ?? graphState?.step ?? null) as string | null;
    if (lastStep) {
      const lastIdx = PIPELINE_STEPS.findIndex((s) => s.key === lastStep);
      if (lastIdx !== -1) {
        if (idx < lastIdx) return "done";
        if (idx === lastIdx) return "failed";
        return "upcoming";
      }
    }
    // Fallback: can't determine step, mark all upcoming
    return "upcoming";
  }

  // Normal in-progress / queued flow
  const cur = PIPELINE_STEPS.findIndex((s) => s.key === currentStatus);
  if (idx < cur) return "done";
  if (idx === cur) return "active";
  return "upcoming";
}

// A run moves through several nodes; poll quickly while it is in flight.
const POLL_ACTIVE_MS = 2500;

export type RunView = {
  id: string;
  question: string;
  status: string;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  graph_state: Record<string, unknown> | null;
  config?: Record<string, unknown> | null;
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
      .select("id, question, status, error, created_at, started_at, completed_at, graph_state, config")
      .eq("id", runId)
      .eq("organization_id", organizationId)
      .maybeSingle();
    if (!error && data) {
      setRun(data as RunView);
    }
  }, [organizationId, runId]);

  useEffect(() => {
    // Poll while the run is in flight so each node's status shows up
    // promptly; stop as soon as it settles (the run is finished, nothing else
    // will change) so an open tab is not polling forever.
    let t: ReturnType<typeof setInterval> | null = null;
    const active = () => !["completed", "failed", "cancelled"].includes(run.status);
    if (active()) {
      t = setInterval(() => void refresh(), POLL_ACTIVE_MS);
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

      {/* Pipeline progress graph */}
      <section className="card p-6 overflow-x-auto relative">
        <h2 className="sr-only">Research pipeline</h2>

        {/* Iteration loop indicator */}
        {(() => {
          const iteration = Number(gs.iteration ?? 0);
          const maxIter = Number(run.config?.max_iterations ?? 3);
          const isLooping = iteration > 0;
          if (!isLooping) return null;

          const isDone = run.status === "completed";
          const isFailed = FAILED_STATUSES.has(run.status);

          // Indices of the two nodes involved in the loop
          const retrieverIdx = 2; // "Retrieving"
          const gapIdx = 4;       // "Gap check"
          const nodeW = 72;
          const connectorW = 36;
          // Left edge of the gap-check node
          const startX = gapIdx * (nodeW + connectorW) + nodeW / 2;
          // Right edge of the retriever node
          const endX = retrieverIdx * (nodeW + connectorW) + nodeW / 2;

          const loopColor = isDone
            ? "text-emerald-500 dark:text-emerald-400"
            : isFailed
            ? "text-rose-500 dark:text-rose-400"
            : "text-amber-400 dark:text-amber-500";
          const badgeBorder = isDone
            ? "border-emerald-300 dark:border-emerald-500/40"
            : isFailed
            ? "border-rose-300 dark:border-rose-500/40"
            : "border-amber-300 dark:border-amber-500/40";
          const badgeBg = isDone
            ? "bg-emerald-50 dark:bg-emerald-500/10"
            : isFailed
            ? "bg-rose-50 dark:bg-rose-500/10"
            : "bg-amber-50 dark:bg-amber-500/10";
          const badgeText = isDone
            ? "text-emerald-700 dark:text-emerald-300"
            : isFailed
            ? "text-rose-700 dark:text-rose-300"
            : "text-amber-700 dark:text-amber-300";
          const fillClass = isDone
            ? "fill-emerald-500 dark:fill-emerald-400"
            : isFailed
            ? "fill-rose-500 dark:fill-rose-400"
            : "fill-amber-400 dark:fill-amber-500";

          return (
            <div className="absolute left-0 right-0" style={{ top: 6, pointerEvents: "none" }}>
              <svg
                width="100%"
                height="56"
                viewBox={`0 0 ${(PIPELINE_STEPS.length - 1) * (nodeW + connectorW) + nodeW} 56`}
                preserveAspectRatio="xMinYMin meet"
                className="overflow-visible"
              >
                {/* Curved arrow from gap-check back to retriever */}
                <path
                  d={`M ${startX} 48 C ${startX} 8, ${endX} 8, ${endX} 48`}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeDasharray={isDone || isFailed ? "none" : "6 4"}
                  className={loopColor}
                />
                {/* Arrowhead at the retriever end */}
                <polygon
                  points={`${endX - 5},52 ${endX},44 ${endX + 5},52`}
                  className={fillClass}
                />
              </svg>
              {/* Iteration badge */}
              <div
                className={`absolute flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-bold shadow-sm ${badgeBorder} ${badgeBg} ${badgeText}`}
                style={{ left: `calc(${((startX + endX) / 2) / ((PIPELINE_STEPS.length - 1) * (nodeW + connectorW) + nodeW) * 100}% - 28px)`, top: -2 }}
              >
                {isDone ? (
                  <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                ) : isFailed ? (
                  <CircleAlert className="h-3 w-3" aria-hidden="true" />
                ) : (
                  <RotateCw className="h-3 w-3 animate-spin" aria-hidden="true" />
                )}
                Iteration {iteration}/{maxIter}
              </div>
            </div>
          );
        })()}

        <div className="flex items-start gap-0 min-w-max" style={{ paddingTop: Number(gs.iteration ?? 0) > 0 ? 40 : 0 }}>
          {PIPELINE_STEPS.map((step, i) => {
            const state = stepState(step.key, run.status, run.graph_state);
            const isLast = i === PIPELINE_STEPS.length - 1;
            const iteration = Number(gs.iteration ?? 0);
            // When looping (iteration > 0), mark retriever/analyzing/gap-check
            // as "on a repeat" so they get a slightly different treatment.
            const isRepeating = iteration > 0 && ["retrieving", "analyzing", "checking_gaps"].includes(step.key);

            return (
              <div key={step.key} className="flex items-start">
                {/* Node */}
                <div className="flex flex-col items-center" style={{ minWidth: 72 }}>
                  <div
                    className={`
                      flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold
                      transition-colors duration-300
                      ${state === "done" ? "bg-emerald-500 text-white shadow-md shadow-emerald-500/20" : ""}
                      ${state === "active" && !isRepeating ? "bg-indigo-500 text-white shadow-lg shadow-indigo-500/30 ring-4 ring-indigo-500/20" : ""}
                      ${state === "active" && isRepeating ? "bg-amber-500 text-white shadow-lg shadow-amber-500/30 ring-4 ring-amber-500/20" : ""}
                      ${state === "upcoming" ? "border-2 border-zinc-200 bg-white text-zinc-400 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-500" : ""}
                      ${state === "failed" ? "bg-rose-500 text-white shadow-md shadow-rose-500/20" : ""}
                    `}
                  >
                    {state === "done" ? (
                      <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
                    ) : state === "active" ? (
                      <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
                    ) : state === "failed" ? (
                      <CircleAlert className="h-5 w-5" aria-hidden="true" />
                    ) : (
                      <span>{i + 1}</span>
                    )}
                  </div>
                  <p
                    className={`mt-2 text-center text-[11px] font-semibold leading-tight
                      ${state === "done" ? "text-emerald-600 dark:text-emerald-400" : ""}
                      ${state === "active" && !isRepeating ? "text-indigo-600 dark:text-indigo-400" : ""}
                      ${state === "active" && isRepeating ? "text-amber-600 dark:text-amber-400" : ""}
                      ${state === "upcoming" ? "text-zinc-400 dark:text-zinc-500" : ""}
                      ${state === "failed" ? "text-rose-600 dark:text-rose-400" : ""}
                    `}
                  >
                    {step.label}
                  </p>
                </div>
                {/* Connector line */}
                {!isLast && (
                  <div className="flex flex-col items-center" style={{ width: 36 }}>
                    <div className="h-5 w-full flex items-center">
                      <div
                        className={`h-[3px] w-full rounded-full transition-colors duration-300
                          ${
                            stepState(step.key, run.status, run.graph_state) === "done"
                              ? "bg-emerald-400 dark:bg-emerald-500"
                              : stepState(step.key, run.status, run.graph_state) === "active"
                              ? "bg-gradient-to-r from-indigo-500 to-zinc-200 dark:to-zinc-700"
                              : "bg-zinc-200 dark:bg-zinc-700"
                          }
                        `}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
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
