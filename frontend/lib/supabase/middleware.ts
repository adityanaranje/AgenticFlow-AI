import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

import { getSupabasePublicEnv } from "@/lib/env";

export async function updateSession(request: NextRequest) {
  const env = getSupabasePublicEnv();

  /*
   * Supabase not configured (missing/blank NEXT_PUBLIC_SUPABASE_URL or
   * NEXT_PUBLIC_SUPABASE_ANON_KEY): fail open instead of crashing every
   * request. Public pages keep working and the auth pages explain what
   * to configure when the user tries to sign in.
   */
  if (!env) {
    console.warn(
      "[supabase] NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are " +
        "not set. Skipping session checks. Add them to frontend/.env and " +
        "restart the dev server.",
    );
    return NextResponse.next();
  }

  let response = NextResponse.next({
    request,
  });

  const supabase = createServerClient(env.url, env.anonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },

      setAll(
        cookiesToSet: {
          name: string;
          value: string;
          options: CookieOptions;
        }[],
      ) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });

        response = NextResponse.next({
          request,
        });

        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const pathname = request.nextUrl.pathname;

  /*
   * Only the auth *pages* should bounce signed-in users away.
   * Do NOT include "/auth/*" here: those are functional endpoints
   * (/auth/logout must run to clear the session, /auth/callback
   * must exchange the PKCE code) and redirecting them would break
   * sign-out and email-link confirmation.
   */
  const isAuthPage = pathname === "/login" || pathname === "/signup";

  const isProtectedRoute =
    pathname.startsWith("/dashboard") ||
    pathname.startsWith("/documents") ||
    pathname.startsWith("/research") ||
    pathname.startsWith("/reports") ||
    pathname.startsWith("/settings");

  if (!user && isProtectedRoute) {
    const url = request.nextUrl.clone();

    url.pathname = "/login";
    url.searchParams.set("redirect", pathname);

    return NextResponse.redirect(url);
  }

  if (user && isAuthPage) {
    const url = request.nextUrl.clone();

    url.pathname = "/dashboard";
    url.search = "";

    return NextResponse.redirect(url);
  }

  return response;
}
