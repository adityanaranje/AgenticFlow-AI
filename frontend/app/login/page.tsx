import type { Metadata } from "next";

import AuthShell from "@/components/auth/AuthShell";
import LoginForm from "@/components/auth/LoginForm";

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
    access_denied: "Access was denied. Please allow access to sign in with Google.",
    server_error: "Google sign-in hit a server error. Please try again later.",
    invalid_request: "The sign-in request was invalid. Please try again.",
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
      <LoginForm initialError={initialError} />
    </AuthShell>
  );
}
