"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CircleAlert, Loader2 } from "lucide-react";

/**
 * Accept button for an invitation.
 *
 * Posts to /api/invitations/{token}/accept, which calls the secured
 * `accept_invitation` database function. The browser never inserts into
 * `organization_members` itself.
 */
export default function AcceptInvitation({
  token,
  organizationId,
}: {
  token: string;
  organizationId: string;
}) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function accept() {
    setError(null);
    setLoading(true);

    try {
      const response = await fetch(`/api/invitations/${token}/accept`, {
        method: "POST",
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          error?: string;
        } | null;
        setError(payload?.error ?? "Could not accept this invitation.");
        setLoading(false);
        return;
      }

      router.push(`/organizations/${organizationId}`);
      router.refresh();
    } catch {
      setError("Could not reach the server. Please try again.");
      setLoading(false);
    }
  }

  return (
    <div className="mt-6 space-y-3">
      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <button
        type="button"
        onClick={accept}
        disabled={loading}
        className="btn-primary btn-block"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          "Accept invitation"
        )}
      </button>

      <Link href="/dashboard" className="btn-secondary btn-block">
        Not now
      </Link>
    </div>
  );
}
