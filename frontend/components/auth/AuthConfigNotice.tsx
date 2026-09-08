"use client";

import { CircleAlert, Terminal } from "lucide-react";

import { ENV_FILE_HINT, getSupabaseEnvStatus } from "@/lib/env";

/**
 * "Supabase isn't configured" notice.
 *
 * Rendered on the auth pages *before* the visitor clicks anything, so a
 * misconfigured environment shows up as a setup checklist instead of a red
 * "Sign-in failed: Error: Missing NEXT_PUBLIC_SUPABASE_URL" toast.
 *
 * In development it names the file to edit, the variables to set and the
 * restart requirement — the three things that actually go wrong. In
 * production it stays short (end users must not see repository layout) and
 * points at the server logs, where the same detail is printed.
 */
export default function AuthConfigNotice() {
  const { configured, issues } = getSupabaseEnvStatus();

  if (configured) return null;

  const isProduction = process.env.NODE_ENV === "production";
  const isSecretKey = issues.some((issue) => issue.code === "secret-key");

  return (
    <div
      role="status"
      aria-live="polite"
      className={[
        "rounded-2xl border p-4 text-sm",
        isSecretKey
          ? "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200"
          : "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200",
      ].join(" ")}
    >
      <p className="flex items-start gap-2 font-semibold">
        <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        {isSecretKey
          ? "A Supabase secret key is configured in the frontend — sign-in is blocked"
          : "Sign-in isn’t configured in this build yet"}
      </p>

      {isProduction ? (
        <p className="mt-2 leading-relaxed opacity-90">
          The server is missing its public Supabase settings. Nobody can sign in
          until they are provided at build time; the exact variables and the fix
          are printed in the server / build logs.
        </p>
      ) : (
        <>
          <ul className="mt-2 space-y-1.5 leading-relaxed">
            {issues.map((issue) => (
              <li key={`${issue.name}-${issue.code}`}>
                <span className="font-medium">{issue.problem}</span>
                <br />
                <span className="opacity-90">{issue.fix}</span>
              </li>
            ))}
          </ul>

          <div className="mt-3 rounded-xl border border-amber-200/80 bg-white/70 p-3 text-xs dark:border-amber-500/20 dark:bg-zinc-900/60">
            <p className="flex items-center gap-1.5 font-semibold text-amber-900 dark:text-amber-200">
              <Terminal className="h-3.5 w-3.5" aria-hidden="true" />
              Check the setup in one command
            </p>
            <p className="mt-2">
              Edit <code className="font-mono">{ENV_FILE_HINT}</code> and
              restart the dev server —{" "}
              <span className="font-medium">
                NEXT_PUBLIC_* values are baked into the browser bundle when the
                server starts
              </span>
              . Turbopack prints{" "}
              <code className="font-mono">Reload env: .env.local</code> when it
              picks an edit up on its own; if that line never appears, restart
              with Ctrl+C. A production build has to be rebuilt.
            </p>
            <pre className="mt-2 overflow-x-auto rounded-lg bg-zinc-900 px-3 py-2 font-mono text-[11px] leading-relaxed text-zinc-100 select-all">
              {`cp frontend/.env.example frontend/.env.local   # PowerShell: Copy-Item frontend/.env.example frontend/.env.local
npm run doctor                                # validates the values + calls Supabase`}
            </pre>
          </div>
        </>
      )}
    </div>
  );
}
