/**
 * AgentFlow AI — Organization server helpers (Phase 3, Part B).
 *
 * Every helper first validates the *authenticated* user against Supabase
 * (via the cookie session) and only then reads organization data. An
 * organization id supplied by the browser is never trusted on its own:
 * `getOrganizationMembership` / `requireOrganizationMembership` confirm a
 * real membership row exists for the current user before returning any data.
 *
 * These helpers run in Server Components / Route Handlers only. They never
 * run in the browser.
 */

import { redirect } from "next/navigation";
import type { User } from "@supabase/supabase-js";

import { createClient } from "@/lib/supabase/server";
import {
  isOrganizationRole,
  type Organization,
  type OrganizationMembership,
  type OrganizationWithMembership,
} from "@/lib/organizations/types";

/** A loosely-typed membership row as returned by the PostgREST join. */
interface MembershipRow {
  id?: string;
  organization_id: string;
  user_id?: string;
  role?: string;
  created_at?: string;
  updated_at?: string | null;
  organizations?: Partial<Organization> | Partial<Organization>[] | null;
}

function asObject<T>(value: T | T[] | null | undefined): T | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return (value as T) ?? null;
}

/** Normalize an RLS-joined membership row into a typed value. */
function normalizeMembership(row: MembershipRow): OrganizationWithMembership {
  const organization = asObject(row.organizations);

  const membership: OrganizationMembership = {
    id: row.id ?? "",
    organization_id: row.organization_id,
    user_id: row.user_id ?? "",
    role: isOrganizationRole(row.role) ? row.role : "viewer",
    created_at: row.created_at ?? new Date().toISOString(),
    updated_at: row.updated_at ?? null,
  };

  return {
    membership,
    organization: {
      id: organization?.id ?? row.organization_id,
      name: organization?.name ?? "Organization",
      slug: organization?.slug ?? "",
      created_by: organization?.created_by,
      created_at: organization?.created_at ?? row.created_at ?? "",
      updated_at: organization?.updated_at ?? null,
    },
  };
}

/**
 * Resolve the authenticated user from the request session.
 * Returns `null` (never throws) when there is no valid session.
 */
export async function getCurrentUser(): Promise<User | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return user ?? null;
}

/** Organizations the current user belongs to, with their role. */
export async function getUserOrganizations(): Promise<
  OrganizationWithMembership[]
> {
  const user = await getCurrentUser();
  if (!user) return [];

  const supabase = await createClient();

  const { data } = await supabase
    .from("organization_members")
    .select(
      "id, organization_id, user_id, role, created_at, updated_at, organizations ( id, name, slug, created_by, created_at, updated_at )",
    )
    .eq("user_id", user.id);

  return (data ?? []).map((row) => normalizeMembership(row as MembershipRow));
}

/**
 * Fetch a single membership for the *current* user, or `null` when they are
 * not a member (or not signed in). Organization ids from the browser are
 * never trusted — this confirms the membership against Supabase.
 */
export async function getOrganizationMembership(
  organizationId: string,
): Promise<OrganizationWithMembership | null> {
  const user = await getCurrentUser();
  if (!user) return null;

  const supabase = await createClient();

  const { data } = await supabase
    .from("organization_members")
    .select(
      "id, organization_id, user_id, role, created_at, updated_at, organizations ( id, name, slug, created_by, created_at, updated_at )",
    )
    .eq("organization_id", organizationId)
    .eq("user_id", user.id)
    .maybeSingle();

  if (!data) return null;

  return normalizeMembership(data as unknown as MembershipRow);
}

/**
 * Resolve the current user's membership in `organizationId`, or redirect
 * when they are signed out (-> /login) or not a member (-> /dashboard).
 *
 * Use in Server Components/Pages where the page must not render for
 * non-members. Non-members receive no organization data.
 */
export async function requireOrganizationMembership(
  organizationId: string,
): Promise<OrganizationWithMembership> {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/login");
  }

  const membership = await getOrganizationMembership(organizationId);

  if (!membership) {
    // Member-only tenant data must not be rendered for non-members.
    redirect("/dashboard");
  }

  return membership;
}
