import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

import { getSupabaseAnonKey, getSupabaseUrl } from "@/lib/env";

/**
 * Sign-out endpoint (POST /auth/logout).
 *
 * The middleware deliberately lets signed-in users reach this route
 * (see lib/supabase/middleware.ts). The response is built FIRST and
 * the Supabase session cookies are cleared by writing straight onto
 * that response, so the redirect to /login reliably arrives with
 * expired session cookies.
 */
export async function POST(request: NextRequest) {
  const response = NextResponse.redirect(new URL("/login", request.url));

  const supabase = createServerClient(getSupabaseUrl(), getSupabaseAnonKey(), {
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
        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  try {
    await supabase.auth.signOut();
  } catch {
    // Fall through: the session cookies are still expired below, so
    // the user is signed out locally even if the revocation call
    // fails (e.g. network error).
  }

  // Defensive: expire any remaining Supabase session cookies
  // (default name pattern: sb-<project-ref>-auth-token).
  for (const cookie of request.cookies.getAll()) {
    if (cookie.name.startsWith("sb-")) {
      response.cookies.set(cookie.name, "", {
        path: "/",
        maxAge: 0,
        expires: new Date(0),
      });
    }
  }

  return response;
}
