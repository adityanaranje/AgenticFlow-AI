import { NextResponse } from "next/server";

import { getSupabasePublicEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

/**
 * AgentFlow AI — Invitation acceptance (Phase 3, §16).
 *
 * POST /api/invitations/{token}/accept
 *
 * Delegates entirely to the secured `accept_invitation` database function,
 * which runs `security definer` and:
 *   - requires an authenticated caller,
 *   - requires the invitation to be pending and unexpired,
 *   - requires the invitation email to match the caller's own email,
 *   - creates the membership row with the invited role.
 *
 * The browser is never granted insert rights on `organization_members`.
 */

export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;

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
      { error: "Sign in to accept this invitation." },
      { status: 401 },
    );
  }

  const { data, error } = await supabase.rpc("accept_invitation", {
    invitation_token: token,
  });

  if (error) {
    // The function raises with meaningful SQLSTATEs.
    const status =
      error.code === "P0002"
        ? 404
        : error.code === "42501"
          ? 403
          : error.code === "23514" || error.code === "P0001"
            ? 409
            : 500;

    return NextResponse.json({ error: error.message }, { status });
  }

  const membership = Array.isArray(data) ? data[0] : data;

  return NextResponse.json({ membership }, { status: 200 });
}
