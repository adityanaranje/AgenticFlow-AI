import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, BookOpenText, FileText, Link2 } from "lucide-react";

import OrgHeader from "@/components/organizations/OrgHeader";
import { getUserOrganizations, requireOrganizationMembership } from "@/lib/organizations/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Report" };

type SourceRow = {
  id: string;
  citation: string;
  title: string | null;
  url: string | null;
  source_type: string;
  metadata: { page_number?: number | null; retrieval_score?: number | null } | null;
};

export default async function ReportDetailPage({
  params,
}: {
  params: Promise<{ organizationId: string; reportId: string }>;
}) {
  const { organizationId, reportId } = await params;
  const { organization } = await requireOrganizationMembership(organizationId);
  const [allMemberships, supabase] = await Promise.all([getUserOrganizations(), createClient()]);

  const orgPath = `/organizations/${organization.id}`;
  const { data: report } = await supabase
    .from("reports")
    .select("id, title, summary, content, confidence, sections, created_at")
    .eq("id", reportId)
    .eq("organization_id", organization.id)
    .maybeSingle();

  let sources: SourceRow[] = [];
  if (report) {
    const { data } = await supabase
      .from("report_sources")
      .select("id, citation, title, url, source_type, metadata")
      .eq("report_id", reportId)
      .order("created_at", { ascending: true });
    sources = (data ?? []) as SourceRow[];
  }

  const sections = (report?.sections ?? {}) as Record<string, string>;
  const sectionEntries = sections && Object.keys(sections).length > 0
    ? Object.entries(sections)
    : null;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <OrgHeader
        organizations={allMemberships.map((m) => ({ organization: m.organization, role: m.membership.role }))}
        currentOrganizationId={organization.id}
      />
      <main className="mx-auto max-w-3xl space-y-8 px-6 py-10">
        <Link
          href={`${orgPath}/reports`}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-500 transition hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to reports
        </Link>

        {!report ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-6 py-10 text-center text-sm text-rose-600 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
            This report was not found in this organization.
          </div>
        ) : (
          <>
            <header>
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-indigo-500">
                <FileText className="h-3.5 w-3.5" aria-hidden="true" /> Report
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-white">
                {report.title}
              </h1>
              {report.confidence != null && (
                <span className="mt-3 inline-block rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                  {Math.round(report.confidence * 100)}% confidence
                </span>
              )}
            </header>

            {sectionEntries ? (
              <section className="space-y-6">
                {sectionEntries.map(([heading, body]) => (
                  <article key={heading} className="card p-6">
                    <h2 className="text-base font-semibold text-zinc-900 dark:text-white">{heading}</h2>
                    <div className="prose-invert mt-3 space-y-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
                      {(body as string).split("\n").filter((line) => line.trim()).map((line, i) => (
                        <p key={i}>{line}</p>
                      ))}
                    </div>
                  </article>
                ))}
              </section>
            ) : (
              <section className="card whitespace-pre-wrap p-6 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
                {report.content}
              </section>
            )}

            <section>
              <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
                <Link2 className="h-5 w-5 text-indigo-500" aria-hidden="true" /> Sources ({sources.length})
              </h2>
              {sources.length === 0 ? (
                <p className="text-sm text-zinc-400">No grounded sources recorded for this report.</p>
              ) : (
                <ol className="space-y-3">
                  {sources.map((s) => (
                    <li key={s.id} className="rounded-2xl border border-zinc-200 bg-white px-5 py-4 dark:border-zinc-800 dark:bg-zinc-900">
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm font-medium text-zinc-900 dark:text-white">
                          <BookOpenText className="mr-1.5 inline h-4 w-4 text-zinc-400" aria-hidden="true" />
                          {s.title ?? "Source"}
                        </p>
                        <span className="shrink-0 rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-semibold text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300">
                          {s.citation}
                        </span>
                      </div>
                      {s.metadata?.page_number != null && (
                        <p className="mt-1 text-xs text-zinc-400">Page {s.metadata.page_number}</p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
