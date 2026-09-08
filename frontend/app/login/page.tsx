import type { Metadata } from "next";

import AuthShell from "@/components/auth/AuthShell";
import LoginForm from "@/components/auth/LoginForm";
import { getOAuthRedirectPlan } from "@/lib/auth-setup.server";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to AgentFlow AI.",
};

function friendlySignInError(
  code: string | null,
  message: string | null,
): string | null {
  if (!code && !message) return null;

  const map: Record<string, string> = {
    missing_code: "The sign-in link was incomplete. Please try again.",
    access_denied:
      "Google did not authorize this request. If it said \u201cthis app's request is " +
      "invalid\u201d, the Authorized redirect URI in Google Cloud must be your " +
      "Supabase project's https://<project-ref>.supabase.co/auth/callback \u2014 see " +
      "\u201cGoogle sign-in setup\u201d below for the exact strings.",
    redirect_uri_mismatch:
      "Google refused the redirect URL. Google Cloud must list your Supabase " +
      "project's /auth/callback as the Authorized redirect URI; this app's own " +
      "callback URL belongs in Supabase -> Authentication -> URL Configuration " +
      "-> Redirect URLs. The exact values are in \u201cGoogle sign-in setup\u201d below.",
    server_error: "Google sign-in hit a server error. Please try again later.",
    invalid_request:
      "The sign-in request was invalid — usually an unknown provider or a " +
      "redirect URL Supabase is not allowed to use. Check the Google provider " +
      "is enabled and the URLs in \u201cGoogle sign-in setup\u201d below are pasted " +
      "into the right consoles.",
    email_conflict: "This email is already linked to another sign-in method.",
  };

  return map[code ?? ""] ?? message ?? "Sign-in failed. Please try again.";
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;

  const first = (value: string | string[] | undefined) =>
    typeof value === "string" ? value : Array.isArray(value) ? value[0] : undefined;

  const initialError = friendlySignInError(
    first(params.error) ?? null,
    first(params.message) ?? null,
  );

  // Dev-only: the exact URLs Google and Supabase must be told about.
  const oauthPlan = await getOAuthRedirectPlan();

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to continue to your research workspace."
      footer={
        <>
          Don&apos;t have an account?{" "}
          <a
            href="/signup"
            className="font-semibold text-indigo-600 transition hover:text-indigo-500 dark:text-indigo-400"
          >
            Create one
          </a>
        </>
      }
    >
      <LoginForm initialError={initialError} oauthPlan={oauthPlan} />
    </AuthShell>
  );
}
