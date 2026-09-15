import type { Metadata } from "next";
import Link from "next/link";
import { BarChart3, FolderOpen } from "lucide-react";

import OrgHeader from "@/components/organizations/OrgHeader";
import { getUserOrganizations, requireOrganizationMembership } from "@/lib/organizations/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Evaluations" };

type EvalRun = {
  id: string;
  report_id: string | null;
  type: string;
  dataset: string;
  status: string;
  summary: Record<string, unknown> | null;
  created_at: string;
  completed_at: string | null;
};

function fmt(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(d);
}

const statusBadge: Record<string, string> = {
  running: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  failed: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
};

export default async function EvaluationsPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  const { organization } = await requireOrganizationMembership(organizationId);
  const [allMemberships, supabase] = await Promise.all([getUserOrganizations(), createClient()]);

  const { data } = await supabase
    .from("evaluation_runs")
    .select("id, report_id, type, dataset, status, summary, created_at, completed_at")
    .eq("organization_id", organization.id)
    .order("created_at", { ascending: false })
    .limit(100);

  const runs = (data ?? []) as EvalRun[];

  // Pre-fetch report titles for display
  const reportIds = [...new Set(runs.map((r) => r.report_id).filter(Boolean))] as string[];
  let reportTitles: Record<string, string> = {};
  if (reportIds.length > 0) {
    const { data: reports } = await supabase
      .from("reports")
      .select("id, title")
      .in("id", reportIds);
    reportTitles = Object.fromEntries((reports ?? []).map((r) => [r.id, r.title]));
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <OrgHeader
        organizations={allMemberships.map((m) => ({ organization: m.organization, role: m.membership.role }))}
        currentOrganizationId={organization.id}
      />
      <main className="mx-auto max-w-4xl space-y-8 px-6 py-10">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-indigo-500">
            <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" /> {organization.name}
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            Evaluations
          </h1>
          <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400">
            Quality metrics for generated reports — citation correctness, groundedness, relevance and more.
          </p>
        </div>

        {runs.length === 0 ? (
          <div className="rounded-2xl border-2 border-dashed border-zinc-300 bg-white/60 px-6 py-14 text-center dark:border-zinc-700 dark:bg-zinc-900/40">
            <FolderOpen className="mx-auto h-8 w-8 text-zinc-300 dark:text-zinc-600" />
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              No evaluations yet. Run an evaluation from a report page.
            </p>
            <Link href={`/organizations/${organization.id}/reports`} className="btn-primary mt-5">
              View reports
            </Link>
          </div>
        ) : (
          <ul className="divide-y divide-zinc-100 overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
            {runs.map((run) => {
              const metrics = (run.summary as { metrics?: Record<string, number> })?.metrics;
              const overall = metrics
                ? Math.round(
                    (Object.values(metrics).filter((v) => typeof v === "number") as number[])
                      .reduce((a, b) => a + b, 0) /
                      Object.values(metrics).filter((v) => typeof v === "number").length *
                      100
                  )
                : null;

              return (
                <li key={run.id}>
                  <Link
                    href={`/organizations/${organization.id}/evaluations/${run.id}`}
                    className="flex items-center justify-between gap-3 px-5 py-4 transition hover:bg-zinc-50 dark:hover:bg-zinc-800/60"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-zinc-900 dark:text-white">
                        {run.report_id ? (reportTitles[run.report_id] ?? "Report evaluation") : "Evaluation"}
                      </p>
                      <p className="mt-0.5 text-xs text-zinc-400">{fmt(run.created_at)}</p>
                    </div>
                    <div className="shrink-0 flex items-center gap-3">
                      {overall != null && (
                        <span className="text-sm font-bold tabular-nums text-zinc-700 dark:text-zinc-300">
                          {overall}%
                        </span>
                      )}
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${statusBadge[run.status] ?? statusBadge.running}`}>
                        {run.status}
                      </span>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </div>
  );
}
