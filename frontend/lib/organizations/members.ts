/**
 * AgentFlow AI — Member & invitation server helpers (Phase 3, §16).
 *
 * These run in Server Components / Route Handlers only, using the caller's
 * Supabase cookie session — so every read and write passes through RLS and
 * the `organization_members_guard` trigger
 * (`database/migrations/015_member_management.sql`).
 *
 * SECURITY NOTE: the checks in `lib/organizations/rbac.ts` shape the UI, but
 * the database is the boundary. Nothing here grants privileges the caller's
 * own session does not already have.
 */

import "server-only";

import { createClient } from "@/lib/supabase/server";
import {
  isOrganizationRole,
  type OrganizationRole,
} from "@/lib/organizations/types";

export interface OrganizationMember {
  id: string;
  user_id: string;
  role: OrganizationRole;
  created_at: string;
  full_name: string | null;
  avatar_url: string | null;
}

export type InvitationStatus =
  | "pending"
  | "accepted"
  | "revoked"
  | "declined";

export interface OrganizationInvitation {
  id: string;
  organization_id: string;
  email: string;
  role: OrganizationRole;
  status: InvitationStatus;
  expires_at: string;
  created_at: string;
  /** When the invitee accepted or declined; null while still pending. */
  responded_at: string | null;
}

function asObject<T>(value: T | T[] | null | undefined): T | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return (value as T) ?? null;
}

/** Members of an organization, with their profile, oldest first. */
export async function listOrganizationMembers(
  organizationId: string,
): Promise<OrganizationMember[]> {
  const supabase = await createClient();

  const { data } = await supabase
    .from("organization_members")
    // `!left` forces a LEFT join: a member whose profile row is missing
    // (or unreadable) still appears, with a null profile, instead of
    // being silently dropped from the roster.
    .select(
      "id, user_id, role, created_at, profiles!left ( id, full_name, avatar_url )",
    )
    .eq("organization_id", organizationId)
    .order("created_at", { ascending: true });

  return (data ?? []).map((row) => {
    const profile = asObject(
      row.profiles as
        | { full_name?: string | null; avatar_url?: string | null }
        | { full_name?: string | null; avatar_url?: string | null }[]
        | null,
    );

    return {
      id: row.id as string,
      user_id: row.user_id as string,
      role: isOrganizationRole(row.role) ? row.role : "viewer",
      created_at: row.created_at as string,
      full_name: profile?.full_name ?? null,
      avatar_url: profile?.avatar_url ?? null,
    };
  });
}

/**
 * Invitations sent by an organization. Pass `null` for `status` to get
 * the full history (pending + answered), which is what the members page
 * shows so senders can see who accepted or declined.
 *
 * RLS restricts the rows to members; only admins/owners are shown this
 * list in the UI.
 */
export async function listOrganizationInvitations(
  organizationId: string,
  status: InvitationStatus | null = "pending",
): Promise<OrganizationInvitation[]> {
  const supabase = await createClient();

  let query = supabase
    .from("organization_invitations")
    .select(
      "id, organization_id, email, role, status, expires_at, created_at, responded_at",
    )
    .eq("organization_id", organizationId);

  if (status) query = query.eq("status", status);

  const { data } = await query.order("created_at", { ascending: false });

  return (data ?? []).map((row) => ({
    id: row.id as string,
    organization_id: row.organization_id as string,
    email: row.email as string,
    role: isOrganizationRole(row.role) ? row.role : "viewer",
    status: (row.status as InvitationStatus) ?? "pending",
    expires_at: row.expires_at as string,
    created_at: row.created_at as string,
    responded_at: (row.responded_at as string | null) ?? null,
  }));
}

/** Absolute URL an invitee should open to accept an invitation. */
export function invitationLink(token: string, origin: string): string {
  return `${origin.replace(/\/$/, "")}/invitations/${token}`;
}

/** An incoming invitation request shown in the invitee's dashboard. */
export interface IncomingInvitation {
  id: string;
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  role: OrganizationRole;
  invited_by_name: string;
  created_at: string;
  expires_at: string;
}

/**
 * Invitation requests addressed to the signed-in user.
 *
 * Backed by the `my_pending_invitations()` database function: the invitee
 * is not yet a member, so they cannot read the organization row or the
 * inviter's profile directly. The function is `security definer`, filters
 * on the caller's own verified email, and never returns the token.
 */
export async function listMyPendingInvitations(): Promise<IncomingInvitation[]> {
  const supabase = await createClient();

  const { data } = await supabase.rpc("my_pending_invitations");

  return ((data as IncomingInvitation[] | null) ?? []).map((row) => ({
    ...row,
    role: isOrganizationRole(row.role) ? row.role : "viewer",
  }));
}
