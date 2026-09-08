import { isRedirectUriMismatch } from "@/lib/auth-setup";

/**
 * Translate auth-flow failures into precise, actionable messages.
 *
 * Supabase auth can fail in several very different ways and they all
 * used to surface as one generic "could not be started" text:
 *
 *  1. Environment not configured  -> requireSupabaseEnv() throws a config error
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

  if (/not configured for this build|Missing NEXT_PUBLIC_|is not configured/.test(message)) {
    // The full diagnosis (which variable, which mistake, which command) is on
    // the page above the form and in the dev-server terminal — don't repeat
    // a wall of text inside a red alert box.
    return (
      "Sign-in isn\u2019t configured in this build. The setup checklist above " +
      "says which variable is missing or invalid \u2014 run \u201cnpm run " +
      "doctor\u201d in frontend/ to verify the values, then restart the dev " +
      "server."
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
      "Could not reach the Supabase server. Check your internet connection, " +
      "whether the project is paused in the dashboard, and that " +
      "NEXT_PUBLIC_SUPABASE_URL is your project URL (\u201cnpm run doctor\u201d " +
      "tests exactly this)."
    );
  }

  if (/provider/i.test(message)) {
    return (
      "The Google provider isn\u2019t enabled for this Supabase project. " +
      "Enable it in the Supabase dashboard (Authentication \u2192 Sign In / " +
      "Providers \u2192 Google) and add http://localhost:3000/auth/callback " +
      "(plus your deployed origin) to the allowed redirect URLs."
    );
  }

  // Surface the underlying message — a real reason beats a generic one.
  return message;
}

/** Map an AuthApiError returned (not thrown) by signInWithOAuth. */
export function describeOAuthError(message: string | null): string | null {
  if (!message) return null;

  if (isRedirectUriMismatch(message)) {
    return (
      "Google rejected the redirect URL. In Google Cloud the \u201cAuthorized " +
      "redirect URI\u201d must be YOUR SUPABASE PROJECT's callback " +
      "(https://<project-ref>.supabase.co/auth/callback) \u2014 not this app's " +
      "/auth/callback, which Google never sees. Add this app's origin under " +
      "\u201cAuthorized JavaScript origins\u201d and put this app's callback URL " +
      "in Supabase -> Authentication -> URL Configuration -> Redirect URLs. " +
      "The exact strings are listed in \u201cGoogle sign-in setup\u201d above."
    );
  }

  if (/redirect url.*not allowed|not in.*allow|allowed_redirect/i.test(message)) {
    return (
      "Supabase refused the redirect target because it is not in the project's " +
      "Redirect URLs allow list (Authentication \u2192 URL Configuration). Add " +
      "http://localhost:3000/auth/callback (and your deployed origin) there."
    );
  }

  if (/provider.*not.*(enabled|supported)|is not enabled/i.test(message)) {
    return (
      "Google sign-in isn\u2019t enabled for this Supabase project yet. " +
      "Enable the Google provider in the Supabase dashboard and add " +
      "/auth/callback to its redirect URLs."
    );
  }

  return message;
}
