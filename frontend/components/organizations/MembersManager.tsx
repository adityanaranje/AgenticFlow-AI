"use client";

import { useMemo, useState, type SubmitEvent } from "react";
import { useRouter } from "next/navigation";
import {
  CircleAlert,
  Copy,
  Check,
  Loader2,
  LogOut,
  Mail,
  Trash2,
  UserPlus,
} from "lucide-react";

import {
  canManageOrganization,
  hasMinimumRole,
} from "@/lib/organizations/rbac";
import {
  ORGANIZATION_ROLES,
  ROLE_RANK,
  type OrganizationRole,
} from "@/lib/organizations/types";

/**
 * Member management UI: invite people, change roles, remove members,
 * revoke pending invitations and leave the organization.
 *
 * SECURITY NOTE: everything here is UX. Each action calls a route handler
 * that re-authenticates the caller, and PostgreSQL RLS plus the
 * `organization_members_guard` trigger are the real boundary — a tampered
 * client cannot grant itself a role it is not allowed to grant.
 */

export interface MemberView {
  user_id: string;
  role: OrganizationRole;
  full_name: string | null;
}

export interface InvitationView {
  id: string;
  email: string;
  role: OrganizationRole;
  expires_at: string;
}

const roleStyles: Record<string, string> = {
  owner: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  admin: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
  researcher:
    "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  viewer: "bg-zinc-100 text-zinc-600 dark:bg-zinc-500/15 dark:text-zinc-300",
};

const roleHelp: Record<OrganizationRole, string> = {
  owner: "Full control, including billing and deleting the organization.",
  admin: "Manage members, documents and every workspace module.",
  researcher: "Upload documents and run research.",
  viewer: "Read-only access to documents, research and reports.",
};

export default function MembersManager({
  organizationId,
  currentUserId,
  currentRole,
  members: initialMembers,
  invitations: initialInvitations,
}: {
  organizationId: string;
  currentUserId: string;
  currentRole: OrganizationRole;
  members: MemberView[];
  invitations: InvitationView[];
}) {
  const router = useRouter();

  const [members, setMembers] = useState(initialMembers);
  const [invitations, setInvitations] = useState(initialInvitations);

  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<OrganizationRole>("viewer");
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const canManage = canManageOrganization(currentRole);

  // You may only hand out roles at or below your own; only an owner may
  // grant 'owner'.
  const assignableRoles = useMemo(
    () =>
      ORGANIZATION_ROLES.filter(
        (role) => ROLE_RANK[role] <= ROLE_RANK[currentRole],
      ),
    [currentRole],
  );

  const ownerCount = members.filter((m) => m.role === "owner").length;

  function reset() {
    setError(null);
    setNotice(null);
  }

  async function handleInvite(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    reset();
    setInviteUrl(null);

    const trimmed = email.trim();
    if (!trimmed) {
      setError("Enter an email address.");
      return;
    }

    setInviting(true);

    try {
      const response = await fetch(
        `/api/organizations/${organizationId}/members`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: trimmed, role: inviteRole }),
        },
      );

      const payload = (await response.json().catch(() => null)) as {
        invitation?: InvitationView;
        invite_url?: string;
        error?: string;
      } | null;

      if (!response.ok || !payload?.invitation) {
        setError(payload?.error ?? "Could not send that invitation.");
        return;
      }

      setInvitations((current) => [payload.invitation as InvitationView, ...current]);
      setInviteUrl(payload.invite_url ?? null);
      setNotice(`Invitation created for ${payload.invitation.email}.`);
      setEmail("");
      router.refresh();
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setInviting(false);
    }
  }

  async function handleRoleChange(userId: string, role: OrganizationRole) {
    reset();
    setBusyId(userId);

    const previous = members;
    setMembers((current) =>
      current.map((m) => (m.user_id === userId ? { ...m, role } : m)),
    );

    try {
      const response = await fetch(
        `/api/organizations/${organizationId}/members/${userId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role }),
        },
      );

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          error?: string;
        } | null;
        setMembers(previous);
        setError(payload?.error ?? "Could not update that role.");
        return;
      }

      setNotice("Role updated.");
      router.refresh();
    } catch {
      setMembers(previous);
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleRemove(userId: string, label: string) {
    reset();

    const leaving = userId === currentUserId;
    const message = leaving
      ? "Leave this organization? You will lose access to its documents and research."
      : `Remove ${label} from this organization?`;

    if (!window.confirm(message)) return;

    setBusyId(userId);

    try {
      const response = await fetch(
        `/api/organizations/${organizationId}/members/${leaving ? "me" : userId}`,
        { method: "DELETE" },
      );

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          error?: string;
        } | null;
        setError(payload?.error ?? "Could not remove that member.");
        return;
      }

      if (leaving) {
        router.push("/dashboard");
        return;
      }

      setMembers((current) => current.filter((m) => m.user_id !== userId));
      setNotice(`${label} was removed.`);
      router.refresh();
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleRevoke(invitationId: string, invitedEmail: string) {
    reset();
    setBusyId(invitationId);

    try {
      const response = await fetch(
        `/api/organizations/${organizationId}/invitations/${invitationId}`,
        { method: "DELETE" },
      );

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          error?: string;
        } | null;
        setError(payload?.error ?? "Could not revoke that invitation.");
        return;
      }

      setInvitations((current) => current.filter((i) => i.id !== invitationId));
      setNotice(`Invitation to ${invitedEmail} was revoked.`);
      router.refresh();
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function copyInviteLink() {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy the link — select and copy it manually.");
    }
  }

  /** Whether the current user may act on a given member row. */
  function canActOn(member: MemberView) {
    if (member.user_id === currentUserId) return false;
    if (!canManage) return false;
    if (member.role === "owner" && currentRole !== "owner") return false;
    return ROLE_RANK[member.role] <= ROLE_RANK[currentRole];
  }

  return (
    <div className="space-y-8">
      {/* Feedback */}
      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}
      {notice && !error && (
        <div
          role="status"
          className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300"
        >
          {notice}
        </div>
      )}

      {/* Invite */}
      {canManage && (
        <section className="card p-6">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-900 dark:text-white">
            <UserPlus className="h-4 w-4 text-indigo-500" aria-hidden="true" />
            Invite a member
          </h2>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            If they already have an account, the request appears on their
            dashboard to accept or decline.
          </p>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {roleHelp[inviteRole]}
          </p>

          <form
            onSubmit={handleInvite}
            className="mt-4 flex flex-col gap-3 sm:flex-row"
          >
            <label className="sr-only" htmlFor="invite-email">
              Email address
            </label>
            <input
              id="invite-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="teammate@company.com"
              autoComplete="off"
              className="input-field flex-1"
              disabled={inviting}
            />

            <label className="sr-only" htmlFor="invite-role">
              Role
            </label>
            <select
              id="invite-role"
              value={inviteRole}
              onChange={(event) =>
                setInviteRole(event.target.value as OrganizationRole)
              }
              className="input-field sm:w-44 capitalize"
              disabled={inviting}
            >
              {assignableRoles.map((role) => (
                <option key={role} value={role} className="capitalize">
                  {role}
                </option>
              ))}
            </select>

            <button
              type="submit"
              className="btn-primary justify-center"
              disabled={inviting}
            >
              {inviting ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                "Send invite"
              )}
            </button>
          </form>

          {inviteUrl && (
            <div className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 dark:border-indigo-500/30 dark:bg-indigo-500/10">
              <p className="text-xs font-medium text-indigo-800 dark:text-indigo-200">
                They will see this request when they sign in. If they do not
                have an account yet, share this link — it works once, for
                their email address only.
              </p>
              <div className="mt-2 flex items-center gap-2">
                <code className="flex-1 truncate rounded-lg bg-white px-3 py-2 font-mono text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-200">
                  {inviteUrl}
                </code>
                <button
                  type="button"
                  onClick={copyInviteLink}
                  className="btn-secondary px-3 py-2"
                  aria-label="Copy invitation link"
                >
                  {copied ? (
                    <Check className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <Copy className="h-4 w-4" aria-hidden="true" />
                  )}
                </button>
              </div>
            </div>
          )}
        </section>
      )}

      {/* Members */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-zinc-900 dark:text-white">
          Members ({members.length})
        </h2>

        <div className="card divide-y divide-zinc-100 dark:divide-zinc-800">
          {members.map((member) => {
            const isSelf = member.user_id === currentUserId;
            const label = member.full_name ?? "Unnamed member";
            const editable = canActOn(member);
            const lastOwner = member.role === "owner" && ownerCount <= 1;

            return (
              <div
                key={member.user_id}
                className="flex flex-wrap items-center justify-between gap-3 px-6 py-4"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-sm font-semibold text-zinc-500 dark:bg-zinc-800 dark:text-zinc-300">
                    {label.charAt(0).toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-800 dark:text-zinc-100">
                      {label}
                      {isSelf && (
                        <span className="ml-2 text-xs font-normal text-zinc-400">
                          you
                        </span>
                      )}
                    </p>
                    <p className="truncate text-xs text-zinc-400">
                      {roleHelp[member.role]}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {editable ? (
                    <select
                      aria-label={`Role for ${label}`}
                      value={member.role}
                      disabled={busyId === member.user_id || lastOwner}
                      onChange={(event) =>
                        handleRoleChange(
                          member.user_id,
                          event.target.value as OrganizationRole,
                        )
                      }
                      className="input-field w-36 py-1.5 text-xs capitalize"
                    >
                      {assignableRoles.map((role) => (
                        <option key={role} value={role} className="capitalize">
                          {role}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
                        roleStyles[member.role] ?? roleStyles.viewer
                      }`}
                    >
                      {member.role}
                    </span>
                  )}

                  {(editable || isSelf) && (
                    <button
                      type="button"
                      onClick={() => handleRemove(member.user_id, label)}
                      disabled={busyId === member.user_id || lastOwner}
                      title={
                        lastOwner
                          ? "An organization must always have at least one owner."
                          : isSelf
                            ? "Leave this organization"
                            : `Remove ${label}`
                      }
                      aria-label={isSelf ? "Leave organization" : `Remove ${label}`}
                      className="rounded-lg p-2 text-zinc-400 transition hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-red-500/10"
                    >
                      {busyId === member.user_id ? (
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                      ) : isSelf ? (
                        <LogOut className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      )}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Pending invitations */}
      {canManage && invitations.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-zinc-900 dark:text-white">
            Pending invitations ({invitations.length})
          </h2>

          <div className="card divide-y divide-zinc-100 dark:divide-zinc-800">
            {invitations.map((invitation) => (
              <div
                key={invitation.id}
                className="flex flex-wrap items-center justify-between gap-3 px-6 py-4"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
                    <Mail className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-800 dark:text-zinc-100">
                      {invitation.email}
                    </p>
                    <p className="text-xs text-zinc-400">
                      Expires{" "}
                      {new Date(invitation.expires_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
                      roleStyles[invitation.role] ?? roleStyles.viewer
                    }`}
                  >
                    {invitation.role}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleRevoke(invitation.id, invitation.email)}
                    disabled={busyId === invitation.id}
                    className="btn-secondary px-3 py-1.5 text-xs"
                  >
                    {busyId === invitation.id ? (
                      <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                    ) : (
                      "Revoke"
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {!canManage && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          You need the admin or owner role to invite or manage members.
          {hasMinimumRole(currentRole, "viewer") &&
            " You can still leave this organization."}
        </p>
      )}
    </div>
  );
}
