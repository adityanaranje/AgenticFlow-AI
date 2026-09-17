"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, CircleAlert, Loader2, UserPlus } from "lucide-react";

import type { IncomingInvitation } from "@/lib/organizations/members";

/**
 * "You have been invited" inbox, rendered at the top of the dashboard.
 *
 * Works like a social follow request: the invitee sees who invited them and
 * to which organization, and accepts or declines in place. Both actions go
 * through /api/invitations/{id}/respond, which calls the secured
 * `respond_to_invitation` database function — the browser never writes a
 * membership row and never handles the invitation token.
 */

const roleStyles: Record<string, string> = {
  owner: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  admin: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
  researcher:
    "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  viewer: "bg-zinc-100 text-zinc-600 dark:bg-zinc-500/15 dark:text-zinc-300",
};

export default function InvitationRequests({
  invitations: initial,
}: {
  invitations: IncomingInvitation[];
}) {
  const router = useRouter();
  const [invitations, setInvitations] = useState(initial);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (invitations.length === 0) return null;

  async function respond(invitation: IncomingInvitation, accept: boolean) {
    setError(null);
    setBusyId(invitation.id);

    try {
      const response = await fetch(
        `/api/invitations/${invitation.id}/respond`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ accept }),
        },
      );

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          error?: string;
        } | null;
        setError(payload?.error ?? "Could not answer that invitation.");
        return;
      }

      setInvitations((current) =>
        current.filter((item) => item.id !== invitation.id),
      );

      if (accept) {
        router.push(`/organizations/${invitation.organization_id}`);
      }
      router.refresh();
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="animate-fade-up">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
          <UserPlus className="h-5 w-5 text-indigo-500" aria-hidden="true" />
          Invitations
        </h2>
        <span className="rounded-full bg-indigo-600 px-2 py-0.5 text-xs font-semibold text-white">
          {invitations.length}
        </span>
      </div>

      {error && (
        <div
          role="alert"
          className="mb-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <div className="card divide-y divide-zinc-100 dark:divide-zinc-800">
        {invitations.map((invitation) => (
          <div
            key={invitation.id}
            className="flex flex-wrap items-center justify-between gap-4 p-5"
          >
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500/15 to-violet-500/15 text-indigo-600 ring-1 ring-indigo-500/20 dark:text-indigo-400">
                <Building2 className="h-5 w-5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-zinc-900 dark:text-white">
                  {invitation.organization_name}
                </p>
                <p className="mt-0.5 truncate text-xs text-zinc-500 dark:text-zinc-400">
                  <span className="font-medium">
                    {invitation.invited_by_name}
                  </span>{" "}
                  invited you to join as{" "}
                  <span
                    className={`ml-0.5 inline-flex rounded-full px-1.5 py-0.5 font-semibold capitalize ${
                      roleStyles[invitation.role] ?? roleStyles.viewer
                    }`}
                  >
                    {invitation.role}
                  </span>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => respond(invitation, false)}
                disabled={busyId === invitation.id}
                className="btn-secondary px-4 py-2 text-xs"
              >
                Decline
              </button>
              <button
                type="button"
                onClick={() => respond(invitation, true)}
                disabled={busyId === invitation.id}
                className="btn-primary px-4 py-2 text-xs"
              >
                {busyId === invitation.id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  "Accept"
                )}
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
