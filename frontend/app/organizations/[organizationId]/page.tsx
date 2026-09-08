import type { ComponentType } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import {
  FileSearch,
  FileText,
  FolderOpen,
  LogOut,
  Microscope,
  ShieldCheck,
  Users,
} from "lucide-react";

import OrganizationSwitcher from "@/components/organizations/OrganizationSwitcher";
import Logo from "@/components/brand/Logo";
import {
  getUserOrganizations,
  requireOrganizationMembership,
} from "@/lib/organizations/server";
import { canManageOrganization } from "@/lib/organizations/rbac";
import type { OrganizationRole } from "@/lib/organizations/types";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Organization",
};

const roleStyles: Record<string, string> = {
  owner: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  admin: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
  researcher:
    "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  viewer: "bg-zinc-100 text-zinc-600 dark:bg-zinc-500/15 dark:text-zinc-300",
};

interface Member {
  user_id: string;
  role: string;
  full_name: string | null;
}

export default async function OrganizationPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;

  // Validates the authenticated user AND their membership. Non-members and
  // signed-out users are redirected before any tenant data is read.
  const { organization, membership } =
    await requireOrganizationMembership(organizationId);

  const [allMemberships, supabase] = await Promise.all([
    getUserOrganizations(),
    createClient(),
  ]);

  const role = membership.role as OrganizationRole;

  const [docCount, researchCount, reportCount, memberRows] = await Promise.all([
    supabase
      .from("documents")
      .select("id", { count: "exact", head: true })
      .eq("organization_id", organization.id),
    supabase
      .from("research_runs")
      .select("id", { count: "exact", head: true })
      .eq("organization_id", organization.id),
    supabase
      .from("reports")
      .select("id", { count: "exact", head: true })
      .eq("organization_id", organization.id),
    supabase
      .from("organization_members")
      .select(
        "user_id, role, profiles ( id, full_name )",
      )
      .eq("organization_id", organization.id),
  ]);

  const members: Member[] = (memberRows.data ?? []).map((row) => {
    const profiles = Array.isArray(row.profiles)
      ? row.profiles[0]
      : row.profiles;
    return {
      user_id: row.user_id,
      role: row.role,
      full_name: profiles?.full_name ?? null,
    };
  });

  const workspaceCards = [
    {
      icon: FileText,
      title: "Documents",
      count: docCount.count ?? 0,
      description: "Knowledge base files for this organization.",
      href: `/organizations/${organization.id}/documents`,
    },
    {
      icon: Microscope,
      title: "Research",
      count: researchCount.count ?? 0,
      description: "Agentic research runs.",
      href: `/organizations/${organization.id}/research`,
    },
    {
      icon: FileSearch,
      title: "Reports",
      count: reportCount.count ?? 0,
      description: "Generated, cited reports.",
      href: `/organizations/${organization.id}/reports`,
    },
  ];

  const workspaceCardInner = (
    title: string,
    Icon: ComponentType<{ className?: string }>,
    count: number,
    description: string,
  ) => (
    <>
      <div className="flex items-center justify-between">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <span className="text-2xl font-semibold text-zinc-900 dark:text-white">
          {count}
        </span>
      </div>
      <h3 className="mt-4 text-sm font-semibold text-zinc-900 dark:text-white">{title}</h3>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{description}</p>
    </>
  );

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      {/* Top bar */}
      <header className="sticky top-0 z-10 border-b border-zinc-200/70 bg-white/80 backdrop-blur-lg dark:border-zinc-800/70 dark:bg-zinc-950/80">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3.5">
          <Link href="/dashboard" aria-label="AgentFlow AI dashboard">
            <Logo size="sm" />
          </Link>

          <div className="flex items-center gap-2.5">
            <OrganizationSwitcher
              organizations={allMemberships.map((m) => ({
                organization: m.organization,
                role: m.membership.role,
              }))}
              currentOrganizationId={organization.id}
            />
            <form action="/auth/logout" method="POST">
              <button
                type="submit"
                title="Sign out"
                aria-label="Sign out"
                className="btn-secondary rounded-full px-3.5 py-2"
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
              </button>
            </form>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-10 px-6 py-10">
        {/* Header */}
        <section className="relative overflow-hidden rounded-3xl bg-zinc-950 px-8 py-9 text-white shadow-2xl shadow-indigo-950/20">
          <div aria-hidden="true" className="absolute inset-0">
            <div className="absolute -right-16 -top-24 h-64 w-64 rounded-full bg-indigo-600/40 blur-3xl" />
            <div className="absolute bottom-0 left-1/4 h-56 w-56 rounded-full bg-violet-600/25 blur-3xl" />
          </div>

          <div className="relative flex flex-col justify-between gap-6 md:flex-row md:items-center">
            <div className="flex items-center gap-4">
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-xl font-bold text-white shadow-lg shadow-indigo-500/30">
                {organization.name.trim().charAt(0).toUpperCase()}
              </span>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-semibold tracking-tight">
                    {organization.name}
                  </h1>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
                      roleStyles[role] ?? roleStyles.viewer
                    }`}
                  >
                    <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                    {role}
                  </span>
                </div>
                <p className="mt-1 font-mono text-sm text-zinc-400">
                  {organization.slug}
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Workspace module counts */}
        <section>
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
            <FolderOpen className="h-5 w-5 text-indigo-500" aria-hidden="true" />
            Organization workspace
          </h2>
          <div className="grid gap-5 sm:grid-cols-3">
            {workspaceCards.map(({ icon: Icon, title, count, description, href }) => {
              const inner = (
                <span className="card block p-6 transition hover:-translate-y-0.5 hover:shadow-md hover:shadow-zinc-900/5 dark:hover:shadow-black/30">
                  {workspaceCardInner(title, Icon, count, description)}
                </span>
              );
              return href ? (
                <Link key={title} href={href} className="block">
                  {inner}
                </Link>
              ) : (
                <article key={title} className="card p-6 opacity-70">
                  {workspaceCardInner(title, Icon, count, description)}
                </article>
              );
            })}
          </div>
          <p className="mt-4 text-xs text-zinc-400">
            Documents are live. Research and reports open in the next phases.
          </p>
        </section>

        {/* Members */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
              <Users className="h-5 w-5 text-indigo-500" aria-hidden="true" />
              Members
            </h2>
            {canManageOrganization(role) && (
              <span className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-600 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-300">
                You can manage members
              </span>
            )}
          </div>

          <div className="card divide-y divide-zinc-100 dark:divide-zinc-800">
            {members.length === 0 ? (
              <p className="p-6 text-sm text-zinc-500 dark:text-zinc-400">
                No members yet.
              </p>
            ) : (
              members.map((member) => (
                <div
                  key={member.user_id}
                  className="flex items-center justify-between gap-3 px-6 py-4"
                >
                  <div className="flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-full bg-zinc-100 text-sm font-semibold text-zinc-500 dark:bg-zinc-800 dark:text-zinc-300">
                      {(member.full_name ?? "?").charAt(0).toUpperCase()}
                    </span>
                    <span className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
                      {member.full_name ?? "Unnamed member"}
                    </span>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
                      roleStyles[member.role] ?? roleStyles.viewer
                    }`}
                  >
                    {member.role}
                  </span>
                </div>
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
