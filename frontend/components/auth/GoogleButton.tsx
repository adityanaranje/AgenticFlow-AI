"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import GoogleIcon from "@/components/auth/GoogleIcon";
import { createClient } from "@/lib/supabase/client";

/**
 * "Continue with Google" button (Supabase OAuth).
 *
 * On success supabase-js redirects the browser to Google and, after
 * consent, back to `/auth/callback` where the PKCE code is exchanged
 * (the code verifier is persisted in cookies by createBrowserClient).
 *
 * Requires the Google provider to be enabled in the Supabase
 * project dashboard (Authentication -> Providers -> Google).
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
        setError(signInError.message);
        setLoading(false);
      }
      // On success the browser is navigated to Google — nothing to do.
    } catch {
      setError("Google sign-in could not be started. Please try again.");
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
          className="mt-2 text-center text-xs font-medium text-rose-600 dark:text-rose-400"
        >
          {error}
        </p>
      )}
    </div>
  );
}
