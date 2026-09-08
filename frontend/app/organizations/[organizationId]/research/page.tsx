import type { Metadata } from "next";
import Link from "next/link";
import { Microscope, Sparkles } from "lucide-react";

import NewResearchForm from "@/components/research/NewResearchForm";
import OrgHeader from "@/components/organizations/OrgHeader";
import {
  getUserOrganizations,
  requireOrganizationMembership,
} from "@/lib/organizations/server";
import type { OrganizationRole } from "@/lib/organizations/types";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Research" };

type RunRow = {
  id: string;
  question: string;
  status: string;
  error: string | null;
  created_at: string;
  completed_at: string | null;
};

const statusMeta: Record<string, string> = {
  queued: "bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-200",
  planning: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  retrieving: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  analyzing: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  checking_gaps: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  synthesizing: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
  validating: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  failed: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
  cancelled: "bg-zinc-200 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300",
};

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(d);
}

export default async function ResearchPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  const { organization, membership } = await requireOrganizationMembership(organizationId);
  const [allMemberships, supabase] = await Promise.all([getUserOrganizations(), createClient()]);

  const { data } = await supabase
    .from("research_runs")
    .select("id, question, status, error, created_at, completed_at")
    .eq("organization_id", organization.id)
    .order("created_at", { ascending: false })
    .limit(50);

  const runs = (data ?? []) as RunRow[];
  const role = membership.role as OrganizationRole;
  const canResearch = ["owner", "admin", "researcher"].includes(role);

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <OrgHeader
        organizations={allMemberships.map((m) => ({ organization: m.organization, role: m.membership.role }))}
        currentOrganizationId={organization.id}
      />
      <main className="mx-auto max-w-4xl space-y-10 px-6 py-10">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-indigo-500">
            <Microscope className="h-3.5 w-3.5" aria-hidden="true" /> {organization.name}
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            Agentic research
          </h1>
          <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400">
            Ask a question and an AI agent plans, retrieves from your knowledge base,
            detects gaps and writes a cited report.
          </p>
        </div>

        <section className="card p-6">
          <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-900 dark:text-white">
            <Sparkles className="h-4 w-4 text-indigo-500" aria-hidden="true" /> New research
          </h2>
          <div className="mt-4">
            <NewResearchForm organizationId={organization.id} canResearch={canResearch} />
          </div>
        </section>

        <section>
          <h2 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
            Research history
          </h2>
          {runs.length === 0 ? (
            <div className="rounded-2xl border-2 border-dashed border-zinc-300 bg-white/60 px-6 py-12 text-center text-sm text-zinc-400 dark:border-zinc-700 dark:bg-zinc-900/40">
              No research runs yet. Start your first one above.
            </div>
          ) : (
            <ul className="divide-y divide-zinc-100 overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
              {runs.map((run) => (
                <li key={run.id}>
                  <Link
                    href={`/organizations/${organization.id}/research/${run.id}`}
                    className="flex items-center justify-between gap-3 px-5 py-4 transition hover:bg-zinc-50 dark:hover:bg-zinc-800/60"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-zinc-900 dark:text-white">{run.question}</p>
                      <p className="mt-0.5 text-xs text-zinc-400">{formatDate(run.created_at)}</p>
                    </div>
                    <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${statusMeta[run.status] ?? statusMeta.queued}`}>
                      {run.status.replace("_", " ")}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
