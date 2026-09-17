import { NextResponse } from "next/server";

import { getSupabasePublicEnv } from "@/lib/env";
import { canManageOrganization } from "@/lib/organizations/rbac";
import { isOrganizationRole, ROLE_RANK } from "@/lib/organizations/types";
import { createClient } from "@/lib/supabase/server";

/**
 * AgentFlow AI — Single member API (Phase 3, §16).
 *
 * PATCH  /api/organizations/{organizationId}/members/{userId}  change role
 * DELETE /api/organizations/{organizationId}/members/{userId}  remove / leave
 *
 * The checks below produce clear messages; the database guard trigger
 * (migration 015) independently enforces the same invariants:
 *   - an organization always keeps at least one owner,
 *   - only an owner grants/revokes 'owner',
 *   - nobody changes their own role or outranks themselves.
 *
 * `userId` may be the literal "me", which means "leave this organization".
 */

export const dynamic = "force-dynamic";

function error(message: string, status: number) {
  return NextResponse.json({ error: message }, { status });
}

/** Map a Postgres error raised by the guard trigger onto an HTTP status. */
function fromPostgres(err: { code?: string; message?: string } | null) {
  if (!err) return error("Something went wrong.", 500);
  if (err.code === "42501" || err.code === "P0001") {
    return error(err.message ?? "Not permitted.", 403);
  }
  if (err.code === "23514") return error(err.message ?? "Not permitted.", 409);
  return error(err.message ?? "Something went wrong.", 500);
}

async function context(organizationId: string) {
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

/** How many owners the organization has right now. */
async function ownerCount(
  supabase: Awaited<ReturnType<typeof createClient>>,
  organizationId: string,
) {
  const { count } = await supabase
    .from("organization_members")
    .select("id", { count: "exact", head: true })
    .eq("organization_id", organizationId)
    .eq("role", "owner");

  return count ?? 0;
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ organizationId: string; userId: string }> },
) {
  const { organizationId, userId } = await params;

  const ctx = await context(organizationId);
  if (ctx.response) return ctx.response;
  const { supabase, user, role } = ctx;

  if (!canManageOrganization(role)) {
    return error("Only an admin or owner can change roles.", 403);
  }

  if (userId === user.id || userId === "me") {
    return error("You cannot change your own role.", 403);
  }

  let body: { role?: unknown };
  try {
    body = (await request.json()) as { role?: unknown };
  } catch {
    return error("A JSON body with a role is required.", 400);
  }

  const nextRole = typeof body.role === "string" ? body.role : "";

  if (!isOrganizationRole(nextRole)) return error("Choose a valid role.", 400);

  const { data: target } = await supabase
    .from("organization_members")
    .select("role")
    .eq("organization_id", organizationId)
    .eq("user_id", userId)
    .maybeSingle();

  if (!target) return error("That user is not a member of this organization.", 404);

  const targetRole = target.role as string;

  if (targetRole === nextRole) {
    return NextResponse.json({ member: { user_id: userId, role: nextRole } });
  }

  if (nextRole === "owner" && role !== "owner") {
    return error("Only an owner can grant the owner role.", 403);
  }
  if (targetRole === "owner" && role !== "owner") {
    return error("Only an owner can modify another owner.", 403);
  }
  if (
    ROLE_RANK[nextRole] > ROLE_RANK[role as keyof typeof ROLE_RANK] ||
    ROLE_RANK[targetRole as keyof typeof ROLE_RANK] >
      ROLE_RANK[role as keyof typeof ROLE_RANK]
  ) {
    return error("You cannot assign a role above your own.", 403);
  }
  if (targetRole === "owner" && (await ownerCount(supabase, organizationId)) <= 1) {
    return error(
      "An organization must always have at least one owner. Promote someone else first.",
      409,
    );
  }

  const { data, error: updateError } = await supabase
    .from("organization_members")
    .update({ role: nextRole })
    .eq("organization_id", organizationId)
    .eq("user_id", userId)
    .select("id, user_id, role")
    .maybeSingle();

  if (updateError || !data) return fromPostgres(updateError);

  return NextResponse.json({ member: data });
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ organizationId: string; userId: string }> },
) {
  const { organizationId, userId: rawUserId } = await params;

  const ctx = await context(organizationId);
  if (ctx.response) return ctx.response;
  const { supabase, user, role } = ctx;

  const userId = rawUserId === "me" ? user.id : rawUserId;
  const leaving = userId === user.id;

  if (!leaving && !canManageOrganization(role)) {
    return error("Only an admin or owner can remove members.", 403);
  }

  const { data: target } = await supabase
    .from("organization_members")
    .select("role")
    .eq("organization_id", organizationId)
    .eq("user_id", userId)
    .maybeSingle();

  if (!target) return error("That user is not a member of this organization.", 404);

  const targetRole = target.role as string;

  if (!leaving) {
    if (targetRole === "owner" && role !== "owner") {
      return error("Only an owner can remove another owner.", 403);
    }
    if (
      ROLE_RANK[targetRole as keyof typeof ROLE_RANK] >
      ROLE_RANK[role as keyof typeof ROLE_RANK]
    ) {
      return error("You cannot remove a member with a higher role.", 403);
    }
  }

  if (targetRole === "owner" && (await ownerCount(supabase, organizationId)) <= 1) {
    return error(
      leaving
        ? "You are the last owner. Promote someone else to owner before leaving."
        : "An organization must always have at least one owner.",
      409,
    );
  }

  // A non-admin leaving cannot satisfy the admin-only delete policy, so the
  // secured `leave_organization` function handles that case.
  if (leaving && !canManageOrganization(role)) {
    const { error: rpcError } = await supabase.rpc("leave_organization", {
      target_organization_id: organizationId,
    });
    if (rpcError) return fromPostgres(rpcError);
    return new NextResponse(null, { status: 204 });
  }

  const { error: deleteError } = await supabase
    .from("organization_members")
    .delete()
    .eq("organization_id", organizationId)
    .eq("user_id", userId);

  if (deleteError) return fromPostgres(deleteError);

  return new NextResponse(null, { status: 204 });
}
