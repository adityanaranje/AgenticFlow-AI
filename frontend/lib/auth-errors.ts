/**
 * Translate auth-flow failures into precise, actionable messages.
 *
 * Supabase auth can fail in several very different ways and they all
 * used to surface as one generic "could not be started" text:
 *
 *  1. Environment not configured  -> createClient() throws "Missing NEXT_PUBLIC_..."
 *  2. Browser blocking cookies    -> PKCE verifier cookie write throws (SecurityError)
 *  3. Network / wrong project URL -> fetch to Supabase fails
 *  4. Google provider not enabled -> signInWithOAuth returns a provider error
 *
 * This helper inspects the real error so the UI can say what to fix.
 */
export function describeAuthError(error: unknown): string {
  if (!(error instanceof Error)) {
    return "An unexpected error occurred. Please try again.";
  }

  const message = error.message ?? String(error);

  if (/Missing NEXT_PUBLIC_/.test(message)) {
    return (
      "Sign-in isn\u2019t configured yet. Copy frontend/.env.example to " +
      "frontend/.env.local and set NEXT_PUBLIC_SUPABASE_URL and " +
      "NEXT_PUBLIC_SUPABASE_ANON_KEY, then restart the dev server."
    );
  }

  if (/cookie|storage|SecurityError/i.test(message)) {
    return (
      "Your browser is blocking cookies for this app, and Supabase sign-in " +
      "needs them. Open this page in a full browser tab (or allow cookies " +
      "for this site) and try again."
    );
  }

  if (/failed to fetch|network|load failed|ERR_|fetch/i.test(message)) {
    return (
      "Could not reach the Supabase server. Check your internet connection " +
      "and that NEXT_PUBLIC_SUPABASE_URL points at your project URL."
    );
  }

  if (/provider/i.test(message)) {
    return (
      "The Google provider isn\u2019t enabled for this Supabase project. " +
      "Enable it in the Supabase dashboard (Authentication \u2192 Providers \u2192 " +
      "Google) and add your /auth/callback URL to the allowed redirect URLs."
    );
  }

  // Surface the underlying message — a real reason beats a generic one.
  return message;
}

/** Map an AuthApiError returned (not thrown) by signInWithOAuth. */
export function describeOAuthError(message: string | null): string | null {
  if (!message) return null;

  if (/provider.*not.*(enabled|supported)|is not enabled/i.test(message)) {
    return (
      "Google sign-in isn\u2019t enabled for this Supabase project yet. " +
      "Enable the Google provider in the Supabase dashboard and add " +
      "/auth/callback to its redirect URLs."
    );
  }

  return message;
}
