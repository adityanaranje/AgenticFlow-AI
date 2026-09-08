/**
 * OAuth (Google) redirect wiring — the three lists that must agree.
 *
 * A Google sign-in attempt involves two different callback URLs, and mixing
 * them up is the single most common cause of Google's
 * "Access blocked: This app's request is invalid" (`redirect_uri_mismatch`):
 *
 *   Browser ──► Supabase /auth/v1/authorize?provider=google&redirect_to=APP
 *   Supabase ──► Google /o/oauth2/auth?redirect_uri=SUPABASE/auth/callback   (1)
 *   Google   ──► SUPABASE/auth/callback?code=…                               (1)
 *   Supabase ──► APP/auth/callback?code=…                                    (2)
 *   APP: exchangeCodeForSession(code) — see app/auth/callback/route.ts
 *
 *  (1) Google Cloud only ever sees the SUPABASE project URL. The app's own
 *      `.../auth/callback` must NOT be listed as an Authorized redirect URI —
 *      Google has never heard of that host in this flow.
 *  (2) `redirectTo` (what supabase-js sends as `redirect_to`) must be listed
 *      in Supabase's own Redirect URLs allowlist, not Google's.
 *
 * Everything the developer has to paste is derived here so the UI, the doctor
 * script and the docs can never disagree with the code.
 */

/** Supabase's fixed provider callback path (GoTrue), not the app's route. */
export const SUPABASE_OAUTH_CALLBACK_PATH = "/auth/callback";

/** The app route that exchanges the PKCE code for a session. */
export const APP_AUTH_CALLBACK_PATH = "/auth/callback";

export interface OAuthRedirectPlan {
  /** Project origin, e.g. https://abcdefghijklmno.supabase.co */
  supabaseOrigin: string;
  /** Where the app runs, e.g. http://localhost:3000 */
  appOrigin: string;
  /** Google Cloud → Clients → (Web application) → Authorized JavaScript origins */
  googleJavaScriptOrigins: string[];
  /** Google Cloud → Clients → Authorized redirect URIs — Supabase's URL, not ours */
  googleAuthorizedRedirectUri: string;
  /** Supabase → Authentication → URL Configuration → Site URL */
  supabaseSiteUrl: string;
  /** Supabase → Authentication → URL Configuration → Redirect URLs */
  supabaseRedirectUrls: string[];
  /** The value this app currently sends as `redirect_to`. */
  redirectTo: string;
}

/**
 * Reconstruct the origin the browser used from proxy headers.
 *
 * `x-forwarded-host` / `x-forwarded-proto` come first: behind a preview proxy,
 * Vercel or a tunnel, `host` is the internal address and would produce a URL
 * Google has never heard of. Falls back to `request.nextUrl.origin`.
 */
export function appOriginFromRequestHeaders(headers: {
  host?: string | null;
  forwardedHost?: string | null;
  forwardedProto?: string | null;
  origin?: string | null;
}): string | null {
  const host = (headers.forwardedHost ?? headers.host ?? "").split(",")[0]!.trim();

  if (!host) {
    return headers.origin ? originOf(headers.origin) : null;
  }

  const proto =
    (headers.forwardedProto ?? "").split(",")[0]!.trim() ||
    (/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(host) ? "http" : "https");

  return originOf(`${proto}://${host}`);
}

function originOf(url: string): string | null {
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

/**
 * Build the checklist for a project.
 *
 * `appOrigin` defaults to `window.location.origin` in the browser and to the
 * local dev server otherwise, so the same helper serves the UI and scripts.
 */
export function buildOAuthRedirectPlan(
  supabaseUrl: string,
  appOrigin?: string,
): OAuthRedirectPlan | null {
  const supabaseOrigin = originOf(supabaseUrl);

  if (!supabaseOrigin) return null;

  const fallback =
    appOrigin ??
    (typeof window !== "undefined" ? window.location.origin : "http://localhost:3000");

  const origin = originOf(fallback) ?? fallback.replace(/\/+$/, "");
  const redirectTo = `${origin}${APP_AUTH_CALLBACK_PATH}`;

  const origins = new Set<string>([origin]);

  // `localhost` and `127.0.0.1` are distinct origins for Google's checks, and
  // Next.js dev servers answer on both — register both to rule that out.
  try {
    const parsed = new URL(origin);

    if (parsed.hostname === "localhost") {
      origins.add(`${parsed.protocol}//127.0.0.1${parsed.port ? `:${parsed.port}` : ""}`);
    } else if (parsed.hostname === "127.0.0.1") {
      origins.add(`${parsed.protocol}//localhost${parsed.port ? `:${parsed.port}` : ""}`);
    }
  } catch {
    /* leave the single origin as-is */
  }

  return {
    supabaseOrigin,
    appOrigin: origin,
    googleJavaScriptOrigins: [...origins],
    googleAuthorizedRedirectUri: `${supabaseOrigin}${SUPABASE_OAUTH_CALLBACK_PATH}`,
    supabaseSiteUrl: origin,
    supabaseRedirectUrls: [redirectTo, `${origin}/**`],
    redirectTo,
  };
}

/**
 * Recognize Google's redirect-URI rejection. Google renders this on its own
 * domain, so the browser usually never returns to the app — the message is
 * here for the cases where it does (and for `?error=` links shared by users).
 */
export function isRedirectUriMismatch(message: string | null | undefined): boolean {
  if (!message) return false;

  return /redirect_uri_mismatch|redirect[\s_]*uri|this app'?s request is invalid|access blocked/i.test(
    message,
  );
}
