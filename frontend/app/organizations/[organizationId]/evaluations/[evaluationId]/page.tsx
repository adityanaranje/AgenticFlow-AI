import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, BarChart3, Calendar, FileText } from "lucide-react";

import OrgHeader from "@/components/organizations/OrgHeader";
import EvaluationMetrics from "@/components/evaluations/EvaluationMetrics";
import { getUserOrganizations, requireOrganizationMembership } from "@/lib/organizations/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Evaluation" };

type EvalResult = {
  id: string;
  test_case: string;
  metric: string;
  score: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export default async function EvaluationDetailPage({
  params,
}: {
  params: Promise<{ organizationId: string; evaluationId: string }>;
}) {
  const { organizationId, evaluationId } = await params;
  const { organization } = await requireOrganizationMembership(organizationId);
  const [allMemberships, supabase] = await Promise.all([getUserOrganizations(), createClient()]);

  const { data: run } = await supabase
    .from("evaluation_runs")
    .select("id, report_id, type, dataset, status, summary, created_at, completed_at")
    .eq("id", evaluationId)
    .eq("organization_id", organization.id)
    .maybeSingle();

  let results: EvalResult[] = [];
  if (run) {
    const { data } = await supabase
      .from("evaluation_results")
      .select("id, test_case, metric, score, metadata, created_at")
      .eq("evaluation_run_id", evaluationId)
      .order("created_at", { ascending: true });
    results = (data ?? []) as EvalResult[];
  }

  // Fetch the linked report title if available
  let reportTitle: string | null = null;
  if (run?.report_id) {
    const { data: report } = await supabase
      .from("reports")
      .select("id, title")
      .eq("id", run.report_id)
      .eq("organization_id", organization.id)
      .maybeSingle();
    reportTitle = report?.title ?? null;
  }

  const orgPath = `/organizations/${organization.id}`;

  // Build metrics map from results
  const metrics: Record<string, number> = {};
  for (const r of results) {
    if (r.score != null) {
      metrics[r.metric] = r.score;
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <OrgHeader
        organizations={allMemberships.map((m) => ({ organization: m.organization, role: m.membership.role }))}
        currentOrganizationId={organization.id}
      />
      <main className="mx-auto max-w-3xl space-y-8 px-6 py-10">
        <Link
          href={`${orgPath}/evaluations`}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-500 transition hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to evaluations
        </Link>

        {!run ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-6 py-10 text-center text-sm text-rose-600 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
            This evaluation run was not found in this organization.
          </div>
        ) : (
          <>
            <header>
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-indigo-500">
                <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" /> Evaluation
              </p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
                {reportTitle ?? "Report evaluation"}
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                {run.report_id && (
                  <Link
                    href={`${orgPath}/reports/${run.report_id}`}
                    className="inline-flex items-center gap-1 rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-medium text-zinc-600 transition hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                  >
                    <FileText className="h-3 w-3" aria-hidden="true" />
                    View report
                  </Link>
                )}
                <span className="flex items-center gap-1 text-xs text-zinc-400">
                  <Calendar className="h-3.5 w-3.5" aria-hidden="true" />
                  {new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(run.created_at))}
                </span>
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
                    run.status === "completed"
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
                      : run.status === "failed"
                      ? "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300"
                      : "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300"
                  }`}
                >
                  {run.status}
                </span>
              </div>
            </header>

            {/* Metrics overview */}
            <section className="card p-6">
              <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
                Quality Metrics
              </h2>
              <div className="mt-5">
                <EvaluationMetrics metrics={metrics} />
              </div>
            </section>

            {/* Detailed results table */}
            {results.length > 0 && (
              <section>
                <h2 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
                  Detailed Results
                </h2>
                <div className="card overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-100 dark:border-zinc-800">
                        <th className="px-5 py-3 text-left font-semibold text-zinc-600 dark:text-zinc-300">Metric</th>
                        <th className="px-5 py-3 text-right font-semibold text-zinc-600 dark:text-zinc-300">Score</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                      {results.map((r) => (
                        <tr key={r.id} className="transition hover:bg-zinc-50 dark:hover:bg-zinc-800/40">
                          <td className="px-5 py-3 text-zinc-800 dark:text-zinc-200 capitalize">
                            {r.metric.replace(/_/g, " ")}
                          </td>
                          <td className="px-5 py-3 text-right font-mono text-zinc-900 dark:text-white">
                            {r.score != null ? `${Math.round(r.score * 100)}%` : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
