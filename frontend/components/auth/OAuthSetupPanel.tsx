"use client";

import { KeyRound } from "lucide-react";

import type { OAuthRedirectPlan } from "@/lib/auth-setup";

/**
 * Google OAuth setup sheet — development only.
 *
 * Google rejects the request on its own page ("Access blocked: This app's
 * request is invalid"), so nothing in this app gets to explain it after the
 * fact. This panel prints the exact strings that must match on the Google and
 * Supabase sides, derived from the configured project URL and the origin the
 * request actually arrived on — no guessing, no stale docs.
 *
 * The plan is computed in the page (server) because the caller's origin comes
 * from request headers; this component only renders it, inside a collapsed
 * <details> so it never gets in the way.
 */
export default function OAuthSetupPanel({ plan }: { plan: OAuthRedirectPlan | null }) {
  if (process.env.NODE_ENV === "production" || !plan) return null;

  const rows = [
    {
      where: "Google Cloud → Auth Platform → Clients → your Web client",
      label: "Authorized JavaScript origins — add all",
      values: plan.googleJavaScriptOrigins,
    },
    {
      where: "Google Cloud → Auth Platform → Clients → your Web client",
      label: "Authorized redirect URIs — Supabase's URL, not this app's",
      values: [plan.googleAuthorizedRedirectUri],
    },
    {
      where: "Supabase → Authentication → URL Configuration",
      label: "Site URL",
      values: [plan.supabaseSiteUrl],
    },
    {
      where: "Supabase → Authentication → URL Configuration → Redirect URLs",
      label: "Allow list for the `redirect_to` this app sends",
      values: plan.supabaseRedirectUrls,
    },
  ];

  return (
    <details className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 text-xs dark:border-zinc-800 dark:bg-zinc-950/40">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-zinc-700 dark:text-zinc-300">
        <KeyRound className="h-3.5 w-3.5 text-zinc-400" aria-hidden="true" />
        Google sign-in setup — exact URLs to paste
      </summary>

      <ol className="mt-3 space-y-3">
        {rows.map((row) => (
          <li key={row.label}>
            <p className="text-zinc-500 dark:text-zinc-400">{row.where}</p>
            <p className="font-medium text-zinc-700 dark:text-zinc-300">{row.label}</p>
            <ul className="mt-1 space-y-1">
              {row.values.map((value) => (
                <li
                  key={value}
                  className="overflow-x-auto rounded-lg bg-zinc-900 px-2.5 py-1.5 font-mono text-[11px] text-zinc-100 select-all"
                >
                  {value}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>

      <p className="mt-3 leading-relaxed text-amber-800 dark:text-amber-300">
        The usual mistake: putting <code className="font-mono">{plan.redirectTo}</code> in
        Google&apos;s <span className="font-medium">Authorized redirect URIs</span>. Google
        never sees this app during the provider hop — it must receive{" "}
        <code className="font-mono">{plan.googleAuthorizedRedirectUri}</code>. Your
        app&apos;s callback URL belongs in Supabase&apos;s Redirect URLs list above. After
        saving changes in Google Cloud, wait about a minute for them to propagate and retry.
      </p>
    </details>
  );
}
