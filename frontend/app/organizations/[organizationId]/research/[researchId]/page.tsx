import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Calendar } from "lucide-react";

import OrgHeader from "@/components/organizations/OrgHeader";
import ResearchRunTracker, { type RunView } from "@/components/research/ResearchRunTracker";
import {
  getUserOrganizations,
  requireOrganizationMembership,
} from "@/lib/organizations/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Research" };

export default async function ResearchDetailPage({
  params,
}: {
  params: Promise<{ organizationId: string; researchId: string }>;
}) {
  const { organizationId, researchId } = await params;
  const { organization } = await requireOrganizationMembership(organizationId);
  const [allMemberships, supabase] = await Promise.all([getUserOrganizations(), createClient()]);

  const { data: run } = await supabase
    .from("research_runs")
    .select("id, question, status, error, created_at, started_at, completed_at, graph_state")
    .eq("id", researchId)
    .eq("organization_id", organization.id)
    .maybeSingle();

  const orgPath = `/organizations/${organization.id}`;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <OrgHeader
        organizations={allMemberships.map((m) => ({ organization: m.organization, role: m.membership.role }))}
        currentOrganizationId={organization.id}
      />
      <main className="mx-auto max-w-3xl space-y-8 px-6 py-10">
        <Link
          href={`${orgPath}/research`}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-500 transition hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to research
        </Link>

        {!run ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-6 py-10 text-center text-sm text-rose-600 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
            This research run was not found in this organization.
          </div>
        ) : (
          <ResearchRunTracker
            organizationId={organization.id}
            runId={run.id}
            initial={run as RunView}
          />
        )}

        <p className="flex items-center gap-1.5 text-xs text-zinc-400">
          <Calendar className="h-3.5 w-3.5" aria-hidden="true" />
          Runs are scoped to {organization.name}. You only ever see this
          organization&apos;s research and sources.
        </p>
      </main>
    </div>
  );
}
