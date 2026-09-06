"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BadgeCheck,
  CircleAlert,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  UserRound,
} from "lucide-react";

import GoogleButton from "@/components/auth/GoogleButton";
import { createClient } from "@/lib/supabase/client";

export default function SignupForm() {
  const router = useRouter();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSignup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError(null);
    setMessage(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setLoading(true);

    const supabase = createClient();

    const origin = window.location.origin;

    const { data, error: signupError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: fullName,
        },
        emailRedirectTo: `${origin}/auth/callback`,
      },
    });

    if (signupError) {
      setError(signupError.message);
      setLoading(false);
      return;
    }

    /*
     * Depending on Supabase email-confirmation settings, the session
     * may be immediately available or may require confirmation.
     */
    if (data.session) {
      router.replace("/dashboard");
      router.refresh();
      return;
    }

    setMessage("Account created. Check your email to confirm your account.");
    setLoading(false);
  }

  return (
    <div className="space-y-6">
      <GoogleButton label="Sign up with Google" />

      {/* Divider */}
      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
        <span className="text-xs font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          or with email
        </span>
        <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
      </div>

      <form onSubmit={handleSignup} className="space-y-5" noValidate={false}>
        <div>
          <label htmlFor="signup-name" className="label">
            Full name
          </label>
          <div className="relative">
            <UserRound
              className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
              aria-hidden="true"
            />
            <input
              id="signup-name"
              type="text"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              required
              autoComplete="name"
              placeholder="Ada Lovelace"
              className="input-field pl-10"
            />
          </div>
        </div>

        <div>
          <label htmlFor="signup-email" className="label">
            Email address
          </label>
          <div className="relative">
            <Mail
              className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
              aria-hidden="true"
            />
            <input
              id="signup-email"
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
          <label htmlFor="signup-password" className="label">
            Password
          </label>
          <div className="relative">
            <Lock
              className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
              aria-hidden="true"
            />
            <input
              id="signup-password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
              placeholder="At least 8 characters"
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

        <div>
          <label htmlFor="signup-confirm" className="label">
            Confirm password
          </label>
          <div className="relative">
            <Lock
              className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
              aria-hidden="true"
            />
            <input
              id="signup-confirm"
              type={showPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              autoComplete="new-password"
              placeholder="Repeat your password"
              className="input-field pl-10"
            />
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

        {message && (
          <div
            role="status"
            className="flex items-start gap-2.5 rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-sm text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300"
          >
            <BadgeCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{message}</span>
          </div>
        )}

        <button type="submit" disabled={loading} className="btn-primary btn-block">
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Creating account…
            </>
          ) : (
            <>
              Create account
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </>
          )}
        </button>

        <p className="text-center text-xs leading-relaxed text-zinc-400 dark:text-zinc-500">
          By continuing you agree to the handling of your data in line with
          your organization&apos;s policies.
        </p>
      </form>
    </div>
  );
}
