import { NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);

  const code = searchParams.get("code");
  const redirectTo = searchParams.get("redirect") || "/dashboard";

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

  const supabase = await createClient();

  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(
      new URL(
        `/login?error=exchange_failed&message=${encodeURIComponent(error.message)}`,
        request.url,
      ),
    );
  }

  return NextResponse.redirect(
    new URL(redirectTo.startsWith("/") ? redirectTo : "/dashboard", request.url),
  );
}
