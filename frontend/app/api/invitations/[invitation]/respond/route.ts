import { NextResponse } from "next/server";

import { getSupabasePublicEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

/**
 * AgentFlow AI — Respond to an invitation request (Phase 3, §16).
 *
 * POST /api/invitations/{invitationId}/respond   (id, from the dashboard)   { "accept": true | false }
 *
 * Powers the accept/decline buttons on the dashboard. Delegates to the
 * secured `respond_to_invitation` database function, which requires an
 * authenticated caller, a pending and unexpired invitation, and an email
 * matching the caller's own. The browser never inserts a membership row
 * itself, and never sees the invitation token.
 */

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ invitation: string }> },
) {
  // This route is keyed by the invitation *id* (the dashboard inbox
  // never handles the secret token).
  const { invitation: invitationId } = await params;

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
      { error: "Sign in to answer this invitation." },
      { status: 401 },
    );
  }

  let accept = true;
  try {
    const body = (await request.json()) as { accept?: unknown };
    accept = body?.accept !== false;
  } catch {
    return NextResponse.json(
      { error: "A JSON body with an `accept` boolean is required." },
      { status: 400 },
    );
  }

  const { data, error } = await supabase.rpc("respond_to_invitation", {
    invitation_id: invitationId,
    accept,
  });

  if (error) {
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

  return NextResponse.json({ result: data as string }, { status: 200 });
}
