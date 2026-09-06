import type { Metadata } from "next";

import AuthShell from "@/components/auth/AuthShell";
import SignupForm from "@/components/auth/SignupForm";

export const metadata: Metadata = {
  title: "Create account",
  description: "Create your AgentFlow AI account.",
};

export default function SignupPage() {
  return (
    <AuthShell
      title="Create your account"
      subtitle="Start building your organization&apos;s knowledge base."
      footer={
        <>
          Already have an account?{" "}
          <a
            href="/login"
            className="font-semibold text-indigo-600 transition hover:text-indigo-500 dark:text-indigo-400"
          >
            Sign in
          </a>
        </>
      }
    >
      <SignupForm />
    </AuthShell>
  );
}
