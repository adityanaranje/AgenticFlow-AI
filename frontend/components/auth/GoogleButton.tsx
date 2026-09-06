"use client";

import { useState } from "react";
import { CircleAlert, Loader2 } from "lucide-react";

import GoogleIcon from "@/components/auth/GoogleIcon";
import { describeAuthError, describeOAuthError } from "@/lib/auth-errors";
import { createClient } from "@/lib/supabase/client";

/**
 * "Continue with Google" button (Supabase OAuth).
 *
 * On success supabase-js redirects the browser to Google and, after
 * consent, back to `/auth/callback` where the PKCE code is exchanged
 * (the code verifier is persisted in cookies by createBrowserClient).
 *
 * Failures are inspected and explained precisely (missing env config,
 * blocked cookies, unreachable Supabase, provider disabled) instead of
 * showing a generic message. The technical error is always logged to
 * the console as well.
 */
export default function GoogleButton({ label }: { label?: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGoogleSignIn() {
    setError(null);
    setLoading(true);

    try {
      const supabase = createClient();

      const redirectTo = `${window.location.origin}/auth/callback`;

      const { error: signInError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo,
        },
      });

      if (signInError) {
        // Provider disabled, invalid project, etc. — returned, not thrown.
        console.error("Google sign-in error:", signInError);
        setError(describeOAuthError(signInError.message) ?? signInError.message);
        setLoading(false);
        return;
      }

      // On success the browser is navigated to Google — nothing to do.
    } catch (err) {
      // Thrown failures: missing env config, blocked cookie writes,
      // network errors to Supabase, ...
      console.error("Google sign-in failed:", err);
      setError(describeAuthError(err));
      setLoading(false);
    }
  }

  return (
    <div className="w-full">
      <button
        type="button"
        onClick={handleGoogleSignIn}
        disabled={loading}
        className="btn-secondary w-full"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <GoogleIcon size={18} />
        )}
        {loading ? "Redirecting to Google…" : (label ?? "Continue with Google")}
      </button>

      {error && (
        <p
          role="alert"
          className="mt-2 flex items-start gap-1.5 text-left text-xs leading-relaxed text-rose-600 dark:text-rose-400"
        >
          <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}
