import type { Metadata } from "next";
import { Users } from "lucide-react";

import OrgHeader from "@/components/organizations/OrgHeader";
import MembersManager from "@/components/organizations/MembersManager";
import {
  getCurrentUser,
  getUserOrganizations,
  requireOrganizationMembership,
} from "@/lib/organizations/server";
import {
  listOrganizationInvitations,
  listOrganizationMembers,
} from "@/lib/organizations/members";
import { canManageOrganization } from "@/lib/organizations/rbac";
import type { OrganizationRole } from "@/lib/organizations/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Members",
};

/**
 * Organization member management.
 *
 * Membership is validated server-side before anything renders: signed-out
 * users go to /login and non-members to /dashboard. Any member may view the
 * roster; only admins and owners see the invite form and the role controls
 * (and RLS + the database guard trigger enforce that independently).
 */
export default async function MembersPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;

  const { organization, membership } =
    await requireOrganizationMembership(organizationId);

  const role = membership.role as OrganizationRole;

  const [user, allMemberships, members, invitations] = await Promise.all([
    getCurrentUser(),
    getUserOrganizations(),
    listOrganizationMembers(organization.id),
    canManageOrganization(role)
      ? listOrganizationInvitations(organization.id, "pending")
      : Promise.resolve([]),
  ]);

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
        <header>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
            <Users className="h-6 w-6 text-indigo-500" aria-hidden="true" />
            Members
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Who can access <span className="font-medium">{organization.name}</span>,
            and what they are allowed to do.
          </p>
        </header>

        <MembersManager
          organizationId={organization.id}
          currentUserId={user?.id ?? ""}
          currentRole={role}
          members={members.map((member) => ({
            user_id: member.user_id,
            role: member.role,
            full_name: member.full_name,
          }))}
          invitations={invitations.map((invitation) => ({
            id: invitation.id,
            email: invitation.email,
            role: invitation.role,
            expires_at: invitation.expires_at,
          }))}
        />
      </main>
    </div>
  );
}
