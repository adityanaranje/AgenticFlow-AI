import type { Metadata } from "next";
import { FileText } from "lucide-react";

import OrganizationDocuments, {
  type DocumentRow,
} from "@/components/documents/OrganizationDocuments";
import OrgHeader from "@/components/organizations/OrgHeader";
import {
  getUserOrganizations,
  requireOrganizationMembership,
} from "@/lib/organizations/server";
import type { OrganizationRole } from "@/lib/organizations/types";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Documents",
};

export default async function OrganizationDocumentsPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;

  // Validates the authenticated user AND membership before rendering.
  const { organization, membership } =
    await requireOrganizationMembership(organizationId);

  const [allMemberships, supabase] = await Promise.all([
    getUserOrganizations(),
    createClient(),
  ]);

  const { data } = await supabase
    .from("documents")
    .select("*")
    .eq("organization_id", organization.id)
    .order("created_at", { ascending: false });

  const documents = (data ?? []) as DocumentRow[];
  const role = membership.role as OrganizationRole;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <OrgHeader
        organizations={allMemberships.map((m) => ({
          organization: m.organization,
          role: m.membership.role,
        }))}
        currentOrganizationId={organization.id}
      />

      <main className="mx-auto max-w-4xl space-y-8 px-6 py-10">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-indigo-500">
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            {organization.name}
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            Documents
          </h1>
          <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400">
            Your organization&apos;s knowledge base. Uploaded files are
            extracted, chunked and embedded automatically.
          </p>
        </div>

        <OrganizationDocuments
          organizationId={organization.id}
          initialDocuments={documents}
          canUpload={["owner", "admin", "researcher"].includes(role)}
        />
      </main>
    </div>
  );
}
