import { NextResponse } from "next/server";

import { getSupabasePublicEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

/**
 * AgentFlow AI — Organization creation API (Phase 3, Part B §11).
 *
 * POST /api/organizations
 *
 * Flow:
 *   1. authenticate the request (the caller's Supabase session),
 *   2. validate the organization name,
 *   3. derive a safe slug,
 *   4. call the secured `create_organization` database function (Phase 2),
 *      which runs `security definer` and sets `created_by = auth.uid()`
 *      and the creator's role to 'owner' server-side,
 *   5. return the created organization.
 *
 * The owner membership is NEVER inserted from the browser — it is created by
 * the database function under the caller's authenticated identity.
 */

const MAX_NAME_LENGTH = 120;
const MAX_SLUG_ATTEMPTS = 10;

/** Lowercase, de-accent, hyphenate; never returns an empty string. */
function slugify(input: string): string {
  const base = input
    .toLowerCase()
    .trim()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);

  return base || "organization";
}

function validationError(message: string, field?: string) {
  return NextResponse.json(
    { error: message, ...(field ? { field } : {}) },
    { status: 400 },
  );
}

export async function POST(request: Request) {
  if (!getSupabasePublicEnv()) {
    return NextResponse.json(
      { error: "Supabase is not configured for this build." },
      { status: 503 },
    );
  }

  const supabase = await createClient();

  // 1. Authenticate the caller.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json(
      { error: "Authentication required." },
      { status: 401 },
    );
  }

  // 2. Parse + validate input.
  let body: { name?: unknown };
  try {
    body = (await request.json()) as { name?: unknown };
  } catch {
    return validationError("A JSON body with an organization name is required.");
  }

  const rawName = typeof body?.name === "string" ? body.name : "";
  const name = rawName.trim();

  if (!name) {
    return validationError("Organization name is required.", "name");
  }
  if (name.length > MAX_NAME_LENGTH) {
    return validationError(
      `Organization name must be ${MAX_NAME_LENGTH} characters or fewer.`,
      "name",
    );
  }

  // 3 + 4. Derive a slug and call the secured database function. Because a
  // slug collision surfaces as a Postgres unique-violation, retry with an
  // incrementing suffix instead of trusting a client-supplied slug.
  const baseSlug = slugify(name);

  let lastError: string | null = null;

  for (let attempt = 0; attempt < MAX_SLUG_ATTEMPTS; attempt += 1) {
    const slug = attempt === 0 ? baseSlug : `${baseSlug}-${attempt + 1}`;

    const { data, error } = await supabase.rpc("create_organization", {
      organization_name: name,
      organization_slug: slug,
    });

    if (!error && data) {
      return NextResponse.json(
        { organization: data, role: "owner" },
        { status: 201 },
      );
    }

    // A slug unique-violation means "try the next suffix".
    if (error?.code === "23505") {
      lastError = "slug_taken";
      continue;
    }

    lastError = error?.message ?? "An unexpected error occurred.";
    break;
  }

  if (lastError === "slug_taken") {
    return NextResponse.json(
      { error: "That organization name is already taken. Try another one." },
      { status: 409 },
    );
  }

  return NextResponse.json({ error: lastError }, { status: 500 });
}
