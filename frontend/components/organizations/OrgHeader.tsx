import Link from "next/link";
import { ArrowLeft, LogOut } from "lucide-react";

import Logo from "@/components/brand/Logo";
import OrganizationSwitcher from "@/components/organizations/OrganizationSwitcher";
import type { Organization, OrganizationRole } from "@/lib/organizations/types";

/**
 * App header used inside an organization workspace: brand, an
 * organization switcher listing only the user's organizations, a back link
 * and sign-out.
 */
export default function OrgHeader({
  organizations,
  currentOrganizationId,
}: {
  organizations: Array<{ organization: Organization; role: OrganizationRole }>;
  currentOrganizationId: string;
}) {
  return (
    <header className="sticky top-0 z-10 border-b border-zinc-200/70 bg-white/80 backdrop-blur-lg dark:border-zinc-800/70 dark:bg-zinc-950/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3.5">
        <div className="flex items-center gap-3">
          <Link
            href={`/organizations/${currentOrganizationId}`}
            aria-label="Back to organization"
            className="rounded-lg p-2 text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Link>
          <Link href="/dashboard" aria-label="AgentFlow AI dashboard">
            <Logo size="sm" />
          </Link>
        </div>

        <div className="flex items-center gap-2.5">
          <OrganizationSwitcher
            organizations={organizations}
            currentOrganizationId={currentOrganizationId}
          />
          <form action="/auth/logout" method="POST">
            <button
              type="submit"
              title="Sign out"
              aria-label="Sign out"
              className="btn-secondary rounded-full px-3 py-2"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
            </button>
          </form>
        </div>
      </div>
    </header>
  );
}
