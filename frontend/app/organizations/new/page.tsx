import type { Metadata } from "next";
import { ArrowLeft, Building2 } from "lucide-react";
import Link from "next/link";

import CreateOrganizationForm from "@/components/organizations/CreateOrganizationForm";

export const metadata: Metadata = {
  title: "Create organization",
  description: "Create your first AgentFlow AI organization.",
};

export default function NewOrganizationPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center px-6 py-12">
      <div className="mb-8">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-500 transition hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to dashboard
        </Link>
      </div>

      <div className="card p-8 sm:p-10">
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500/15 to-violet-500/15 text-indigo-600 ring-1 ring-indigo-500/20 dark:text-indigo-400">
          <Building2 className="h-6 w-6" aria-hidden="true" />
        </span>

        <h1 className="mt-5 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
          Create an organization
        </h1>
        <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400">
          Organizations are multi-tenant workspaces. You will become its owner,
          with your own knowledge base for documents, research and reports.
        </p>

        <div className="mt-7">
          <CreateOrganizationForm />
        </div>
      </div>
    </main>
  );
}
