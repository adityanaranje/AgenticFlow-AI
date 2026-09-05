"use client";

import { type SubmitEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { createClient } from "@/lib/supabase/client";

export default function SignupPage() {
  const router = useRouter();

  const [fullName, setFullName] =
    useState("");

  const [email, setEmail] =
    useState("");

  const [password, setPassword] =
    useState("");

  const [confirmPassword, setConfirmPassword] =
    useState("");

  const [error, setError] =
    useState<string | null>(null);

  const [message, setMessage] =
    useState<string | null>(null);

  const [loading, setLoading] =
    useState(false);

  async function handleSignup(
    event: SubmitEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    setError(null);
    setMessage(null);

    if (password !== confirmPassword) {
      setError(
        "Passwords do not match.",
      );

      return;
    }

    if (password.length < 8) {
      setError(
        "Password must be at least 8 characters.",
      );

      return;
    }

    setLoading(true);

    const supabase =
      createClient();

    const origin =
      window.location.origin;

    const {
      data,
      error: signupError,
    } =
      await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            full_name: fullName,
          },
          emailRedirectTo:
            `${origin}/auth/callback`,
        },
      });

    if (signupError) {
      setError(
        signupError.message,
      );

      setLoading(false);
      return;
    }

    /*
     * Depending on Supabase email-confirmation
     * settings, session may be immediately
     * available or may require confirmation.
     */
    if (data.session) {
      router.replace("/dashboard");
      router.refresh();
      return;
    }

    setMessage(
      "Account created. Check your email to confirm your account.",
    );

    setLoading(false);
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: "24px",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "420px",
        }}
      >
        <h1>Create account</h1>

        <p>
          Create your AgentFlow AI account.
        </p>

        <form
          onSubmit={handleSignup}
          style={{
            display: "grid",
            gap: "16px",
            marginTop: "24px",
          }}
        >
          <label>
            Full name
            <input
              type="text"
              value={fullName}
              onChange={(event) =>
                setFullName(
                  event.target.value,
                )
              }
              required
              autoComplete="name"
              style={{
                display: "block",
                width: "100%",
                marginTop: "6px",
                padding: "10px",
              }}
            />
          </label>

          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) =>
                setEmail(
                  event.target.value,
                )
              }
              required
              autoComplete="email"
              style={{
                display: "block",
                width: "100%",
                marginTop: "6px",
                padding: "10px",
              }}
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) =>
                setPassword(
                  event.target.value,
                )
              }
              required
              autoComplete="new-password"
              style={{
                display: "block",
                width: "100%",
                marginTop: "6px",
                padding: "10px",
              }}
            />
          </label>

          <label>
            Confirm password
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) =>
                setConfirmPassword(
                  event.target.value,
                )
              }
              required
              autoComplete="new-password"
              style={{
                display: "block",
                width: "100%",
                marginTop: "6px",
                padding: "10px",
              }}
            />
          </label>

          {error && (
            <p
              role="alert"
              style={{
                color: "crimson",
              }}
            >
              {error}
            </p>
          )}

          {message && (
            <p
              role="status"
              style={{
                color: "green",
              }}
            >
              {message}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
          >
            {loading
              ? "Creating account..."
              : "Create account"}
          </button>
        </form>

        <p
          style={{
            marginTop: "20px",
          }}
        >
          Already have an account?{" "}
          <a href="/login">
            Sign in
          </a>
        </p>
      </div>
    </main>
  );
}