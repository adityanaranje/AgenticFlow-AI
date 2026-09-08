import { NextResponse } from "next/server";

import { safeRedirect } from "@/lib/safe-redirect";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);

  const code = searchParams.get("code");
  // Only ever redirect to a safe internal path (never an external URL).
  const redirectTo = safeRedirect(searchParams.get("redirect"));

  /*
   * OAuth providers (Google) redirect back here with `code` on
   * success or `error` (+ description) on failure. Show failures on
   * the sign-in page instead of silently dropping the user.
   */
  const oauthError = searchParams.get("error");
  const oauthErrorDescription =
    searchParams.get("error_description") || searchParams.get("message");

  if (oauthError) {
    return NextResponse.redirect(
      new URL(
        `/login?error=${encodeURIComponent(oauthError)}&message=${encodeURIComponent(
          oauthErrorDescription ?? "",
        )}`,
        request.url,
      ),
    );
  }

  if (!code) {
    return NextResponse.redirect(
      new URL(
        `/login?error=missing_code&message=${encodeURIComponent(
          "No authorization code was provided by the sign-in provider.",
        )}`,
        request.url,
      ),
    );
  }

  const supabase = await createClient().catch(() => null);

  if (!supabase) {
    // Supabase not configured (missing env): nothing to exchange.
    return NextResponse.redirect(
      new URL(
        `/login?error=missing_config&message=${encodeURIComponent(
          "Supabase is not configured for this build. Add " +
            "NEXT_PUBLIC_SUPABASE_URL and the publishable (or legacy anon) " +
            "key to frontend/.env.local, restart the dev server, and check " +
            "the values with \"npm run doctor\".",
        )}`,
        request.url,
      ),
    );
  }

  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(
      new URL(
        `/login?error=exchange_failed&message=${encodeURIComponent(error.message)}`,
        request.url,
      ),
    );
  }

  return NextResponse.redirect(new URL(redirectTo, request.url));
}
