import { NextResponse } from "next/server";

import { getSupabasePublicEnv } from "@/lib/env";
import { canManageOrganization } from "@/lib/organizations/rbac";
import { isOrganizationRole } from "@/lib/organizations/types";
import { createClient } from "@/lib/supabase/server";

/**
 * AgentFlow AI — Organization members API (Phase 3, §16).
 *
 * POST /api/organizations/{organizationId}/members
 *   Invite somebody by email. When the address already belongs to a
 *   registered user they are added straight away; otherwise a pending
 *   invitation row is created and its acceptance link is returned.
 *
 * Authorization is layered:
 *   1. the caller's Supabase session is resolved server-side,
 *   2. their membership + role is read from `organization_members`
 *      (the client-supplied organization id is never trusted),
 *   3. admin+ is required here for a clear error message,
 *   4. RLS and the `organization_members_guard` trigger remain the
 *      authoritative boundary for the actual write.
 */

export const dynamic = "force-dynamic";

function error(message: string, status: number) {
  return NextResponse.json({ error: message }, { status });
}

/** Resolve the caller and their role, or an error response. */
async function authorize(organizationId: string) {
  if (!getSupabasePublicEnv()) {
    return { response: error("Supabase is not configured for this build.", 503) };
  }

  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) return { response: error("Authentication required.", 401) };

  const { data: membership } = await supabase
    .from("organization_members")
    .select("role")
    .eq("organization_id", organizationId)
    .eq("user_id", user.id)
    .maybeSingle();

  if (!membership) {
    return { response: error("You are not a member of this organization.", 403) };
  }

  return { supabase, user, role: membership.role as string };
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ organizationId: string }> },
) {
  const { organizationId } = await params;

  const auth = await authorize(organizationId);
  if (auth.response) return auth.response;
  const { supabase, user, role } = auth;

  if (!canManageOrganization(role)) {
    return error("Only an admin or owner can invite members.", 403);
  }

  let body: { email?: unknown; role?: unknown; user_id?: unknown };
  try {
    body = (await request.json()) as {
      email?: unknown;
      role?: unknown;
      user_id?: unknown;
    };
  } catch {
    return error("A JSON body with an email or user_id and role is required.", 400);
  }

  const invitedRole = typeof body.role === "string" ? body.role : "viewer";

  if (!isOrganizationRole(invitedRole)) {
    return error("Choose a valid role.", 400);
  }
  if (invitedRole === "owner" && role !== "owner") {
    return error("Only an owner can grant the owner role.", 403);
  }

  // The dashboard "add member" picker sends a user_id chosen from the
  // narrow `search_invitable_users` result set. Resolve it to that user's
  // email through the secured function rather than trusting the browser:
  // `resolve_invitable_email` re-checks that the caller is an admin/owner.
  let email = "";

  if (typeof body.user_id === "string" && body.user_id) {
    const { data: resolved, error: resolveError } = await supabase.rpc(
      "resolve_invitable_email",
      {
        target_organization_id: organizationId,
        target_user_id: body.user_id,
      },
    );

    if (resolveError) {
      return error(resolveError.message, 500);
    }
    if (!resolved) {
      return error("That user could not be found.", 404);
    }

    email = String(resolved).toLowerCase();
  } else {
    email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  }

  if (!email || !/^[^@\s]+@[^@\s.]+\.[^@\s]+$/.test(email)) {
    return error("Enter a valid email address.", 400);
  }

  // Already a member? Say so plainly instead of creating a dead invitation.
  const { data: existingMember } = await supabase
    .from("organization_members")
    .select("user_id, profiles ( full_name )")
    .eq("organization_id", organizationId)
    .eq("user_id", typeof body.user_id === "string" ? body.user_id : "")
    .maybeSingle();

  if (existingMember) {
    return error("That person is already a member of this organization.", 409);
  }

  // Already a pending invitation? Surface a friendly conflict rather than a
  // unique-index violation.
  const { data: pending } = await supabase
    .from("organization_invitations")
    .select("id")
    .eq("organization_id", organizationId)
    .eq("email", email)
    .eq("status", "pending")
    .maybeSingle();

  if (pending) {
    return error("An invitation for that email is already pending.", 409);
  }

  const { data: invitation, error: insertError } = await supabase
    .from("organization_invitations")
    .insert({
      organization_id: organizationId,
      email,
      role: invitedRole,
      invited_by: user.id,
    })
    .select("id, email, role, status, token, expires_at, created_at")
    .maybeSingle();

  if (insertError || !invitation) {
    if (insertError?.code === "23505") {
      return error("An invitation for that email is already pending.", 409);
    }
    return error(
      insertError?.message ?? "Could not create the invitation.",
      insertError?.code === "42501" ? 403 : 500,
    );
  }

  const origin = new URL(request.url).origin;

  return NextResponse.json(
    {
      invitation: {
        id: invitation.id,
        email: invitation.email,
        role: invitation.role,
        status: invitation.status,
        expires_at: invitation.expires_at,
        created_at: invitation.created_at,
      },
      // Returned once, to the inviting admin, so they can share the link.
      invite_url: `${origin}/invitations/${invitation.token}`,
    },
    { status: 201 },
  );
}
