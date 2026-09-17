import { NextResponse } from "next/server";

import { getSupabasePublicEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

/**
 * AgentFlow AI — Find people to invite (Phase 3, §16).
 *
 * GET /api/organizations/{organizationId}/members/search?q=...
 *
 * PRIVACY: this is not a browsable user directory. The underlying
 * `search_invitable_users` database function requires the caller to be an
 * admin/owner of the organization, needs either a full exact email address
 * or a 3+ character name prefix, and never returns anybody's email. See
 * `database/migrations/016_invitation_requests.sql`.
 */

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ organizationId: string }> },
) {
  const { organizationId } = await params;

  if (!getSupabasePublicEnv()) {
    return NextResponse.json(
      { error: "Supabase is not configured for this build." },
      { status: 503 },
    );
  }

  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json(
      { error: "Authentication required." },
      { status: 401 },
    );
  }

  const query = (new URL(request.url).searchParams.get("q") ?? "").trim();

  if (query.length < 3) {
    return NextResponse.json({ users: [] });
  }

  const { data, error } = await supabase.rpc("search_invitable_users", {
    target_organization_id: organizationId,
    search_query: query,
  });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ users: data ?? [] });
}
