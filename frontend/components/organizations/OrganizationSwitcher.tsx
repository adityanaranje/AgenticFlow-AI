"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Check, ChevronsUpDown, Plus } from "lucide-react";

import type {
  Organization,
  OrganizationRole,
} from "@/lib/organizations/types";

/**
 * Organization switcher.
 *
 * Lists ONLY the signed-in user's organizations (the list is resolved
 * server-side against the user's authenticated memberships and passed in as
 * props), highlights the current one, and navigates to its workspace.
 *
 * The current organization context is persisted in the URL
 * (`/organizations/{organizationId}/...`) rather than only in localStorage,
 * so authorization state is never trusted from unverifiable client storage.
 */
export default function OrganizationSwitcher({
  organizations,
  currentOrganizationId,
}: {
  /** The user's own organizations (id + name + role). */
  organizations: Array<{
    organization: Organization;
    role: OrganizationRole;
  }>;
  /** The currently active organization id, if any. */
  currentOrganizationId?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const current =
    organizations.find((o) => o.organization.id === currentOrganizationId) ??
    null;

  const initials = useMemo(() => {
    if (!current) return "?";
    return current.organization.name.trim().charAt(0).toUpperCase();
  }, [current]);

  function goTo(organizationId: string) {
    setOpen(false);
    router.push(`/organizations/${organizationId}`);
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="Switch organization"
        className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:border-zinc-700"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-br from-indigo-500 to-violet-500 text-[11px] font-bold text-white">
          {initials}
        </span>
        <span className="hidden max-w-[10rem] truncate sm:inline">
          {current?.organization.name ?? "No organization"}
        </span>
        <ChevronsUpDown className="h-4 w-4 text-zinc-400" aria-hidden="true" />
      </button>

      {open && (
        <>
          <button
            type="button"
            aria-label="Close organization menu"
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-10 cursor-default"
            tabIndex={-1}
          />
          <div
            role="listbox"
            className="absolute right-0 z-20 mt-2 w-64 overflow-hidden rounded-2xl border border-zinc-200 bg-white p-1.5 shadow-xl shadow-zinc-900/10 dark:border-zinc-800 dark:bg-zinc-900 dark:shadow-black/40"
          >
            <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              Organizations
            </p>

            {organizations.length === 0 ? (
              <p className="px-3 py-2 text-sm text-zinc-500 dark:text-zinc-400">
                You are not part of any organization yet.
              </p>
            ) : (
              <ul className="max-h-72 overflow-y-auto">
                {organizations.map(({ organization, role }) => {
                  const active = organization.id === currentOrganizationId;

                  return (
                    <li key={organization.id}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={active}
                        onClick={() => goTo(organization.id)}
                        className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm transition hover:bg-zinc-100 dark:hover:bg-zinc-800"
                      >
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500/15 to-violet-500/15 text-indigo-600 dark:text-indigo-400">
                          <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium text-zinc-800 dark:text-zinc-100">
                            {organization.name}
                          </span>
                          <span className="block text-[11px] capitalize text-zinc-400">
                            {role}
                          </span>
                        </span>
                        {active && (
                          <Check
                            className="h-4 w-4 text-indigo-500"
                            aria-hidden="true"
                          />
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}

            <button
              type="button"
              onClick={() => {
                setOpen(false);
                router.push("/organizations/new");
              }}
              className="mt-1 flex w-full items-center gap-2 rounded-xl border-t border-zinc-100 px-3 py-2 text-left text-sm font-medium text-indigo-600 transition hover:bg-indigo-50 dark:border-zinc-800 dark:text-indigo-400 dark:hover:bg-indigo-500/10"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Create organization
            </button>
          </div>
        </>
      )}
    </div>
  );
}
