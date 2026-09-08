/**
 * AgentFlow AI — Organization types (Phase 3, Part B).
 *
 * Canonical roles: owner > admin > researcher > viewer.
 *
 * SECURITY NOTE: these types mirror the PostgreSQL role check constraint
 * (`organization_members_role_check`) and the RLS policies in
 * `database/migrations/`. Frontend RBAC (`lib/organizations/rbac.ts`) is a
 * convenience for rendering/UX only — it is NOT the security boundary.
 * PostgreSQL RLS and the backend authorization layer remain authoritative.
 */

export type OrganizationRole = "owner" | "admin" | "researcher" | "viewer";

/** All roles in descending privilege order (index 0 = most privileged). */
export const ORGANIZATION_ROLES: readonly OrganizationRole[] = [
  "owner",
  "admin",
  "researcher",
  "viewer",
];

/** Numeric rank used for comparisons. Higher number = more privileged. */
export const ROLE_RANK: Record<OrganizationRole, number> = {
  owner: 4,
  admin: 3,
  researcher: 2,
  viewer: 1,
};

export function isOrganizationRole(value: unknown): value is OrganizationRole {
  return (
    typeof value === "string" &&
    (ORGANIZATION_ROLES as readonly string[]).includes(value)
  );
}

/** Organization entity, matching `public.organizations`. */
export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_by?: string;
  created_at: string;
  updated_at?: string | null;
}

/** Membership row, matching `public.organization_members`. */
export interface OrganizationMembership {
  id: string;
  organization_id: string;
  user_id: string;
  role: OrganizationRole;
  created_at: string;
  updated_at?: string | null;
  /** Joined organization (populated when the query requests it). */
  organization?: Organization;
}

/** A membership plus its joined organization, fully resolved. */
export interface OrganizationWithMembership {
  organization: Organization;
  membership: OrganizationMembership;
}

/** Resolved current-organization context for a signed-in user. */
export interface OrganizationContext {
  /** The currently active organization, or null when the user has none. */
  currentOrganization: Organization | null;
  /** The viewer's role in the current organization, or null. */
  currentRole: OrganizationRole | null;
  /** Every organization the user is a member of (for the switcher). */
  memberships: OrganizationWithMembership[];
}
