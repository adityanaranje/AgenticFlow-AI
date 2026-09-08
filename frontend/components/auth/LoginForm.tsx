"use client";

import { useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, CircleAlert, Eye, EyeOff, Loader2, Lock, Mail } from "lucide-react";

import AuthConfigNotice from "@/components/auth/AuthConfigNotice";
import GoogleButton from "@/components/auth/GoogleButton";
import { describeAuthError } from "@/lib/auth-errors";
import { getSupabaseEnvStatus } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

export default function LoginForm({ initialError }: { initialError?: string | null }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const redirect = searchParams.get("redirect") || "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(initialError ?? null);
  const [loading, setLoading] = useState(false);

  // Unusable configuration is shown as a setup checklist, not an error.
  const { configured } = getSupabaseEnvStatus();

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!configured) return;

    setError(null);
    setLoading(true);

    try {
      const supabase = createClient();

      const { error: loginError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (loginError) {
        setError(loginError.message);
        setLoading(false);
        return;
      }
    } catch (err) {
      console.error("Sign-in failed:", err);
      setError(describeAuthError(err));
      setLoading(false);
      return;
    }

    router.replace(redirect.startsWith("/") ? redirect : "/dashboard");
    router.refresh();
  }

  return (
    <div className="space-y-6">
      {!configured && <AuthConfigNotice />}

      <GoogleButton />

      {/* Divider */}
      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
        <span className="text-xs font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          or with email
        </span>
        <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
      </div>

      <form onSubmit={handleLogin} className="space-y-5" noValidate={false}>
        <div>
          <label htmlFor="login-email" className="label">
            Email address
          </label>
          <div className="relative">
            <Mail
              className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
              aria-hidden="true"
            />
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
              placeholder="you@company.com"
              className="input-field pl-10"
            />
          </div>
        </div>

        <div>
          <label htmlFor="login-password" className="label">
            Password
          </label>
          <div className="relative">
            <Lock
              className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
              aria-hidden="true"
            />
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••"
              className="input-field pl-10 pr-11"
            />
            <button
              type="button"
              onClick={() => setShowPassword((visible) => !visible)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
            >
              {showPassword ? (
                <EyeOff className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Eye className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
          </div>
        </div>

        {error && (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
          >
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !configured}
          className="btn-primary btn-block"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Signing in…
            </>
          ) : (
            <>
              Sign in
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </>
          )}
        </button>
      </form>
    </div>
  );
}
