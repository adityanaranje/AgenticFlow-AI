import { NextResponse } from "next/server";

import { getSupabasePublicEnv } from "@/lib/env";
import { canManageOrganization } from "@/lib/organizations/rbac";
import { createClient } from "@/lib/supabase/server";

/**
 * AgentFlow AI — Invitation revocation (Phase 3, §16).
 *
 * DELETE /api/organizations/{organizationId}/invitations/{invitationId}
 *
 * Revoking marks the row `revoked` rather than deleting it, so the audit
 * trail of who invited whom survives. RLS restricts updates to admins and
 * owners of the organization.
 */

export const dynamic = "force-dynamic";

function error(message: string, status: number) {
  return NextResponse.json({ error: message }, { status });
}

export async function DELETE(
  _request: Request,
  {
    params,
  }: { params: Promise<{ organizationId: string; invitationId: string }> },
) {
  const { organizationId, invitationId } = await params;

  if (!getSupabasePublicEnv()) {
    return error("Supabase is not configured for this build.", 503);
  }

  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) return error("Authentication required.", 401);

  const { data: membership } = await supabase
    .from("organization_members")
    .select("role")
    .eq("organization_id", organizationId)
    .eq("user_id", user.id)
    .maybeSingle();

  if (!membership) {
    return error("You are not a member of this organization.", 403);
  }

  if (!canManageOrganization(membership.role as string)) {
    return error("Only an admin or owner can revoke invitations.", 403);
  }

  const { data, error: updateError } = await supabase
    .from("organization_invitations")
    .update({ status: "revoked" })
    .eq("id", invitationId)
    .eq("organization_id", organizationId)
    .eq("status", "pending")
    .select("id")
    .maybeSingle();

  if (updateError) {
    return error(updateError.message, updateError.code === "42501" ? 403 : 500);
  }

  if (!data) return error("That invitation is no longer pending.", 409);

  return new NextResponse(null, { status: 204 });
}
