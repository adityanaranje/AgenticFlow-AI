import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import {
  Bot,
  Building2,
  ClipboardCheck,
  FileSearch,
  FolderOpen,
  LogOut,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UserRound,
} from "lucide-react";

import Logo from "@/components/brand/Logo";
import OrganizationSwitcher from "@/components/organizations/OrganizationSwitcher";
import { getUserOrganizations } from "@/lib/organizations/server";
import type { OrganizationRole } from "@/lib/organizations/types";
import { getSupabasePublicEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Dashboard",
};

/*
 * The dashboard renders the signed-in user's session, so it must be
 * rendered per-request (never statically prerendered). force-dynamic
 * also keeps the missing-env guard below from confusing Next's
 * dynamic-usage detection during builds.
 */
export const dynamic = "force-dynamic";

const roleStyles: Record<string, string> = {
  owner: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  admin: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
  researcher:
    "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  viewer: "bg-zinc-100 text-zinc-600 dark:bg-zinc-500/15 dark:text-zinc-300",
};

function formatMemberSince(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en", { month: "short", year: "numeric" }).format(date);
}

const comingSoon = [
  {
    icon: UploadCloud,
    title: "Documents",
    text: "Upload files and build your knowledge base.",
  },
  {
    icon: Bot,
    title: "AI Research",
    text: "Run agentic research against your documents.",
  },
  {
    icon: FileSearch,
    title: "Reports",
    text: "Generate and share cited research reports.",
  },
  {
    icon: ClipboardCheck,
    title: "Evaluations",
    text: "Measure the quality of generated answers.",
  },
];

export default async function DashboardPage() {
  // Supabase env missing → redirect before rendering starts; the auth
  // pages explain how to configure the app when signing in is attempted.
  if (!getSupabasePublicEnv()) {
    console.warn(
      "[dashboard] Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / " +
        "NEXT_PUBLIC_SUPABASE_ANON_KEY). Redirecting to /login.",
    );
    redirect("/login");
  }

  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select("id, full_name, avatar_url")
    .eq("id", user.id)
    .maybeSingle();

  // Resolve the user's organizations + roles against their authenticated
  // memberships (never trusts a client-supplied organization id).
  const myOrganizations = await getUserOrganizations();

  const displayName = profile?.full_name?.trim() || user.email?.split("@")[0] || "there";
  const initial = displayName.charAt(0).toUpperCase();
  const organizations = myOrganizations.map(({ membership, organization }) => ({
    organization,
    role: membership.role as OrganizationRole,
    created_at: membership.created_at,
  }));

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      {/* Top bar */}
      <header className="sticky top-0 z-10 border-b border-zinc-200/70 bg-white/80 backdrop-blur-lg dark:border-zinc-800/70 dark:bg-zinc-950/80">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3.5">
          <Link href="/" aria-label="AgentFlow AI home">
            <Logo size="sm" />
          </Link>

          <div className="flex items-center gap-3">
            <OrganizationSwitcher
              organizations={organizations}
              currentOrganizationId={organizations[0]?.organization.id}
            />

            <span className="hidden items-center gap-2 rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-600 sm:inline-flex dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-[10px] font-bold text-white">
                {initial}
              </span>
              {user.email}
            </span>

            <form action="/auth/logout" method="POST">
              <button
                type="submit"
                title="Sign out"
                aria-label="Sign out"
                className="btn-secondary rounded-full px-3.5 py-2"
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">Sign out</span>
              </button>
            </form>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-10 px-6 py-10">
        {/* Hero */}
        <section className="relative overflow-hidden rounded-3xl bg-zinc-950 px-8 py-10 text-white shadow-2xl shadow-indigo-950/20 sm:px-10">
          <div aria-hidden="true" className="absolute inset-0">
            <div className="absolute -left-20 -top-24 h-72 w-72 rounded-full bg-indigo-600/40 blur-3xl" />
            <div className="absolute -bottom-28 right-0 h-80 w-80 rounded-full bg-violet-600/30 blur-3xl" />
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_20%,rgba(99,102,241,0.18),transparent_55%)]" />
          </div>

          <div className="relative flex flex-col justify-between gap-8 md:flex-row md:items-center">
            <div className="max-w-xl">
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-indigo-300">
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                Dashboard
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Welcome{profile?.full_name ? `, ${profile.full_name.split(" ")[0]}` : ""} 👋
              </h1>
              <p className="mt-3 text-zinc-400">
                Your research workspace for documents, AI research and reports.
              </p>
            </div>

            <div className="flex items-center gap-3 md:flex-col lg:flex-row">
              <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-5 py-4 backdrop-blur">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-lg font-bold text-white shadow-lg shadow-indigo-500/30">
                  {initial}
                </span>
                <div>
                  <p className="text-sm font-semibold">{displayName}</p>
                  <p className="text-xs text-zinc-400">{user.email}</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Organizations */}
        <section className="animate-fade-up anim-delay-1">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <h2 className="flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
                <Building2 className="h-5 w-5 text-indigo-500" aria-hidden="true" />
                Your organizations
              </h2>
              <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
                Multi-tenant workspaces for documents and research.
              </p>
            </div>
            {organizations.length > 0 && (
              <span className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-medium text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
                {organizations.length} {organizations.length === 1 ? "organization" : "organizations"}
              </span>
            )}
          </div>

          {organizations.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-3xl border-2 border-dashed border-zinc-300 bg-white/60 px-6 py-16 text-center dark:border-zinc-700 dark:bg-zinc-900/40">
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-zinc-200 bg-white text-zinc-400 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
                <Building2 className="h-7 w-7" aria-hidden="true" />
              </span>
              <h3 className="mt-5 text-base font-semibold text-zinc-900 dark:text-white">
                You are not part of any organization yet
              </h3>
              <p className="mt-1.5 max-w-sm text-sm text-zinc-500 dark:text-zinc-400">
                Organizations let your team share a knowledge base of documents,
                research and reports. Create your first organization to get
                started.
              </p>
              <Link
                href="/organizations/new"
                className="btn-primary mt-6 px-5"
              >
                <FolderOpen className="h-4 w-4" aria-hidden="true" />
                Create your first organization
              </Link>
            </div>
          ) : (
            <div className="grid gap-5 sm:grid-cols-2">
              {organizations.map(({ organization, role, created_at }, index) => (
                <Link
                  key={organization.id}
                  href={`/organizations/${organization.id}`}
                  className="card animate-fade-up block p-6 transition hover:-translate-y-0.5 hover:shadow-lg hover:shadow-zinc-900/5 dark:hover:shadow-black/30"
                  style={{ animationDelay: `${120 + index * 80}ms` }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500/15 to-violet-500/15 text-indigo-600 ring-1 ring-indigo-500/20 dark:text-indigo-400">
                      <Building2 className="h-6 w-6" aria-hidden="true" />
                    </span>
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
                        roleStyles[role] ?? roleStyles.viewer
                      }`}
                    >
                      <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                      {role}
                    </span>
                  </div>

                  <h3 className="mt-4 text-base font-semibold text-zinc-900 dark:text-white">
                    {organization.name}
                  </h3>
                  <p className="mt-0.5 font-mono text-xs text-zinc-400">
                    {organization.slug}
                  </p>

                  <div className="mt-4 flex items-center gap-1.5 text-xs text-zinc-400">
                    <UserRound className="h-3.5 w-3.5" aria-hidden="true" />
                    Member since {formatMemberSince(created_at) || "recently"}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>

        {/* Coming next */}
        <section className="animate-fade-up anim-delay-2 pb-6">
          <h2 className="mb-5 text-lg font-semibold text-zinc-900 dark:text-white">
            Workspace modules
          </h2>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {comingSoon.map(({ icon: Icon, title, text }) => (
              <article
                key={title}
                className="card group relative overflow-hidden p-6"
              >
                <div
                  aria-hidden="true"
                  className="absolute -right-10 -top-10 h-28 w-28 rounded-full bg-indigo-500/10 blur-2xl transition group-hover:bg-indigo-500/20"
                />
                <span className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                  <Icon className="h-5 w-5" aria-hidden="true" />
                </span>
                <h3 className="relative mt-4 text-sm font-semibold text-zinc-900 dark:text-white">
                  {title}
                </h3>
                <p className="relative mt-1 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
                  {text}
                </p>
                <span className="relative mt-4 inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-600 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-300">
                  Coming next
                </span>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
