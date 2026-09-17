import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { CircleAlert, MailCheck } from "lucide-react";

import Logo from "@/components/brand/Logo";
import AcceptInvitation from "@/components/organizations/AcceptInvitation";
import { getCurrentUser } from "@/lib/organizations/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Join organization",
};

interface InvitationPreview {
  organization_id: string;
  organization_name: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
}

/**
 * Invitation landing page.
 *
 * A signed-in invitee is not yet a member, so they cannot read the
 * organization row directly. The `invitation_preview` database function
 * (migration 015) returns only the safe, non-tenant fields for a token.
 * Acceptance itself goes through `accept_invitation`, which verifies the
 * caller's own email matches the invitation.
 */
export default async function InvitationPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  const user = await getCurrentUser();

  if (!user) {
    // Come back here after signing in.
    redirect(`/login?redirect=${encodeURIComponent(`/invitations/${token}`)}`);
  }

  const supabase = await createClient();

  const { data } = await supabase.rpc("invitation_preview", {
    invitation_token: token,
  });

  const invitation = (Array.isArray(data) ? data[0] : data) as
    | InvitationPreview
    | undefined;

  const emailMatches =
    !!invitation &&
    invitation.email.toLowerCase() === (user.email ?? "").toLowerCase();

  const problem = !invitation
    ? "This invitation link is not valid."
    : invitation.status === "expired"
      ? "This invitation has expired. Ask an admin to send a new one."
      : invitation.status === "revoked"
        ? "This invitation has been revoked."
        : invitation.status === "accepted"
          ? "This invitation has already been used."
          : !emailMatches
            ? `This invitation was sent to ${invitation.email}, but you are signed in as ${user.email}.`
            : null;

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-6 dark:bg-zinc-950">
      <div className="card w-full max-w-md p-8">
        <Logo size="sm" />

        {problem ? (
          <>
            <div className="mt-6 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{problem}</span>
            </div>
            <Link href="/dashboard" className="btn-secondary mt-6 w-full">
              Go to dashboard
            </Link>
          </>
        ) : (
          <>
            <div className="mt-6 flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                <MailCheck className="h-5 w-5" aria-hidden="true" />
              </span>
              <div>
                <h1 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  Join {invitation!.organization_name}
                </h1>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  You have been invited as{" "}
                  <span className="font-medium capitalize">
                    {invitation!.role}
                  </span>
                  .
                </p>
              </div>
            </div>

            <AcceptInvitation
              token={token}
              organizationId={invitation!.organization_id}
            />
          </>
        )}
      </div>
    </main>
  );
}
