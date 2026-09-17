"use client";

import { useEffect, useRef, useState, type SubmitEvent } from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  CircleAlert,
  Loader2,
  Search,
  Send,
  UserPlus,
} from "lucide-react";

import { ORGANIZATION_ROLES, ROLE_RANK } from "@/lib/organizations/types";
import type { OrganizationRole } from "@/lib/organizations/types";

/**
 * Dashboard widget for sending a join request straight to a person —
 * the Instagram/Facebook style "add member" flow.
 *
 * Type a name (3+ characters) or a full email address, pick the person,
 * choose a role and send. They see the request on their own dashboard the
 * next time they sign in and can accept or decline it.
 *
 * SECURITY NOTE: the search is intentionally narrow (admins/owners only,
 * exact email or name prefix, never returns email addresses) and every
 * write is re-authorized server-side by RLS and the
 * `organization_members_guard` trigger. See
 * `database/migrations/016_invitation_requests.sql`.
 */

interface Candidate {
  user_id: string;
  full_name: string | null;
  avatar_url: string | null;
  is_member: boolean;
}

export interface ManageableOrganization {
  id: string;
  name: string;
  role: OrganizationRole;
}

export default function QuickAddMember({
  organizations,
}: {
  organizations: ManageableOrganization[];
}) {
  const router = useRouter();

  const [organizationId, setOrganizationId] = useState(
    organizations[0]?.id ?? "",
  );
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [role, setRole] = useState<OrganizationRole>("viewer");
  const [searching, setSearching] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);

  const requestRef = useRef(0);

  const activeOrganization =
    organizations.find((item) => item.id === organizationId) ?? organizations[0];

  // Never offer a role above the inviter's own.
  const assignableRoles = ORGANIZATION_ROLES.filter(
    (candidate) =>
      ROLE_RANK[candidate] <= ROLE_RANK[activeOrganization?.role ?? "viewer"],
  );

  const looksLikeEmail = /^[^@\s]+@[^@\s.]+\.[^@\s]+$/.test(query.trim());

  // Whether a lookup is warranted at all for the current input.
  const canSearch =
    !selected && query.trim().length >= 3 && organizationId !== "";

  // Debounced directory lookup. Results are only *rendered* when
  // `canSearch` holds (see below), so the effect never has to clear them
  // synchronously — it just skips fetching.
  useEffect(() => {
    if (!canSearch) return;

    const trimmed = query.trim();
    const ticket = ++requestRef.current;

    const timer = window.setTimeout(async () => {
      setSearching(true);
      try {
        const response = await fetch(
          `/api/organizations/${organizationId}/members/search?q=${encodeURIComponent(trimmed)}`,
        );
        const payload = (await response.json().catch(() => null)) as {
          users?: Candidate[];
        } | null;

        // Ignore responses from superseded keystrokes.
        if (ticket === requestRef.current) {
          setResults(payload?.users ?? []);
        }
      } catch {
        if (ticket === requestRef.current) setResults([]);
      } finally {
        if (ticket === requestRef.current) setSearching(false);
      }
    }, 300);

    return () => window.clearTimeout(timer);
  }, [query, organizationId, canSearch]);

  // Stale results from a previous query must never be shown.
  const visibleResults = canSearch ? results : [];

  if (organizations.length === 0) return null;

  async function send(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSentTo(null);

    // We invite by email: either the typed address, or the selected
    // person's id resolved server-side.
    const trimmed = query.trim();

    if (!selected && !looksLikeEmail) {
      setError(
        "Pick someone from the list, or type their full email address.",
      );
      return;
    }

    setSending(true);

    try {
      const response = await fetch(
        `/api/organizations/${organizationId}/members`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            selected
              ? { user_id: selected.user_id, role }
              : { email: trimmed, role },
          ),
        },
      );

      const payload = (await response.json().catch(() => null)) as {
        invitation?: { email: string };
        error?: string;
      } | null;

      if (!response.ok) {
        setError(payload?.error ?? "Could not send that request.");
        return;
      }

      setSentTo(
        selected?.full_name ?? payload?.invitation?.email ?? trimmed,
      );
      setQuery("");
      setSelected(null);
      setResults([]);
      router.refresh();
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="animate-fade-up">
      <div className="mb-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
          <UserPlus className="h-5 w-5 text-indigo-500" aria-hidden="true" />
          Add a member
        </h2>
        <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
          Send a join request — they can accept it from their own dashboard.
        </p>
      </div>

      <form onSubmit={send} className="card space-y-3 p-5">
        {organizations.length > 1 && (
          <div>
            <label className="label" htmlFor="quick-add-org">
              Organization
            </label>
            <select
              id="quick-add-org"
              value={organizationId}
              onChange={(event) => {
                setOrganizationId(event.target.value);
                setSelected(null);
                setResults([]);
              }}
              className="input-field"
              disabled={sending}
            >
              {organizations.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label className="label" htmlFor="quick-add-person">
            Who do you want to add?
          </label>

          {selected ? (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-indigo-200 bg-indigo-50/60 px-3.5 py-2.5 dark:border-indigo-500/30 dark:bg-indigo-500/10">
              <span className="flex min-w-0 items-center gap-2.5">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-xs font-bold text-white">
                  {(selected.full_name ?? "?").charAt(0).toUpperCase()}
                </span>
                <span className="truncate text-sm font-medium text-zinc-800 dark:text-zinc-100">
                  {selected.full_name ?? "Unnamed user"}
                </span>
              </span>
              <button
                type="button"
                onClick={() => {
                  setSelected(null);
                  setQuery("");
                }}
                className="text-xs font-semibold text-indigo-600 hover:underline dark:text-indigo-300"
              >
                Change
              </button>
            </div>
          ) : (
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
                aria-hidden="true"
              />
              <input
                id="quick-add-person"
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by name, or type a full email"
                autoComplete="off"
                className="input-field pl-9"
                disabled={sending}
              />
              {searching && (
                <Loader2
                  className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-zinc-400"
                  aria-hidden="true"
                />
              )}
            </div>
          )}

          {/* Results */}
          {visibleResults.length > 0 && (
            <ul className="mt-2 overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
              {visibleResults.map((candidate) => (
                <li key={candidate.user_id}>
                  <button
                    type="button"
                    disabled={candidate.is_member}
                    onClick={() => {
                      setSelected(candidate);
                      setResults([]);
                    }}
                    className="flex w-full items-center justify-between gap-3 border-b border-zinc-100 bg-white px-3.5 py-2.5 text-left transition last:border-0 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800"
                  >
                    <span className="flex min-w-0 items-center gap-2.5">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-xs font-semibold text-zinc-500 dark:bg-zinc-800 dark:text-zinc-300">
                        {(candidate.full_name ?? "?").charAt(0).toUpperCase()}
                      </span>
                      <span className="truncate text-sm text-zinc-800 dark:text-zinc-100">
                        {candidate.full_name ?? "Unnamed user"}
                      </span>
                    </span>
                    {candidate.is_member && (
                      <span className="shrink-0 text-xs text-zinc-400">
                        Already a member
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {!selected &&
            !searching &&
            query.trim().length >= 3 &&
            visibleResults.length === 0 && (
              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                {looksLikeEmail
                  ? "No account uses that address yet — we'll send them an invitation they can accept after signing up."
                  : "No match. Try their full email address instead."}
              </p>
            )}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="sm:w-44">
            <label className="label" htmlFor="quick-add-role">
              Role
            </label>
            <select
              id="quick-add-role"
              value={role}
              onChange={(event) => setRole(event.target.value as OrganizationRole)}
              className="input-field capitalize"
              disabled={sending}
            >
              {assignableRoles.map((item) => (
                <option key={item} value={item} className="capitalize">
                  {item}
                </option>
              ))}
            </select>
          </div>

          <button
            type="submit"
            className="btn-primary sm:ml-auto"
            disabled={sending || (!selected && !looksLikeEmail)}
          >
            {sending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <>
                <Send className="h-4 w-4" aria-hidden="true" />
                Send request
              </>
            )}
          </button>
        </div>

        {error && (
          <p
            role="alert"
            className="flex items-start gap-2 text-sm text-red-600 dark:text-red-400"
          >
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}

        {sentTo && !error && (
          <p
            role="status"
            className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400"
          >
            <Check className="h-4 w-4" aria-hidden="true" />
            Request sent to {sentTo}.
          </p>
        )}
      </form>
    </section>
  );
}
