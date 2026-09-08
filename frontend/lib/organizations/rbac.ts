/**
 * AgentFlow AI — Organization RBAC helpers (Phase 3, Part B).
 *
 * Small pure helpers that map a membership role onto the capabilities used
 * across the app (view / research / manage / delete).
 *
 * Role hierarchy: viewer < researcher < admin < owner.
 *
 * SECURITY NOTE: frontend RBAC is NOT the security boundary. These helpers
 * only drive what the UI shows / links to for a signed-in user whose
 * membership has already been validated against Supabase. PostgreSQL RLS and
 * the backend authorization layer (backend/app/core/auth.py + rbac.py)
 * remain authoritative and must be re-checked on every privileged action.
 */

import {
  ORGANIZATION_ROLES,
  ROLE_RANK,
  type OrganizationRole,
} from "@/lib/organizations/types";

/** True when `role` meets or exceeds the given `required` role. */
export function hasMinimumRole(
  role: OrganizationRole | string | null | undefined,
  required: OrganizationRole,
): boolean {
  if (!role) return false;
  const actualRank = ROLE_RANK[role as OrganizationRole];
  if (actualRank === undefined) return false;
  return actualRank >= ROLE_RANK[required];
}

/** A member may view the organization's content (any membership). */
export function canView(
  role: OrganizationRole | string | null | undefined,
): boolean {
  return hasMinimumRole(role, "viewer");
}

/** A member may run research / contribute documents (researcher+). */
export function canResearch(
  role: OrganizationRole | string | null | undefined,
): boolean {
  return hasMinimumRole(role, "researcher");
}

/** A member may manage the organization & members (admin+). */
export function canManageOrganization(
  role: OrganizationRole | string | null | undefined,
): boolean {
  return hasMinimumRole(role, "admin");
}

/** Only the owner may delete an organization. */
export function canDeleteOrganization(
  role: OrganizationRole | string | null | undefined,
): boolean {
  return role === "owner";
}

/** Roles at-or-above a given role, used for e.g. role pickers. */
export function rolesAtOrAbove(required: OrganizationRole): OrganizationRole[] {
  const min = ROLE_RANK[required];
  return ORGANIZATION_ROLES.filter((role) => ROLE_RANK[role] >= min);
}
