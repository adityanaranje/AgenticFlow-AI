"use client";

import GoogleIdentityButton from "@/components/auth/GoogleIdentityButton";
import GoogleRedirectButton from "@/components/auth/GoogleRedirectButton";
import { getGoogleIdentityStatus } from "@/lib/env";

/**
 * Google sign-in button — picks the flow the project is configured for.
 *
 * Two flows exist because of what Google's account chooser prints above the
 * account list:
 *
 *   NEXT_PUBLIC_GOOGLE_CLIENT_ID set  -> Google Identity Services.
 *       Google renders its prompt on this page, keyed to the client ID's
 *       Authorized JavaScript origin, so it reads "to continue to
 *       <your domain>". The ID token is passed to signInWithIdToken().
 *
 *   not set (default)                 -> Supabase redirect flow.
 *       signInWithOAuth() sends the browser through
 *       <project-ref>.supabase.co/auth/v1/authorize, so Google names that
 *       host: "to continue to <project-ref>.supabase.co".
 *
 * The identity button degrades to the redirect button by itself when the
 * Google script cannot load, so this choice is never a single point of
 * failure. See the README section "Google consent screen: showing your own
 * domain".
 */
export default function GoogleButton({
  label,
  intent = "signin",
  redirectTo = "/dashboard",
}: {
  label?: string;
  /** Changes Google's own button wording ("Sign up with" vs "Continue with"). */
  intent?: "signin" | "signup";
  /** Internal path to land on after a successful ID-token sign-in. */
  redirectTo?: string;
}) {
  const { enabled, issue } = getGoogleIdentityStatus();

  if (issue && typeof window !== "undefined") {
    console.warn(`[auth] ${issue}`);
  }

  if (enabled) {
    return (
      <GoogleIdentityButton label={label} intent={intent} redirectTo={redirectTo} />
    );
  }

  return <GoogleRedirectButton label={label} />;
}
