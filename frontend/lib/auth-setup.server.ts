import { headers } from "next/headers";

import {
  appOriginFromRequestHeaders,
  buildOAuthRedirectPlan,
  type OAuthRedirectPlan,
} from "@/lib/auth-setup";
import { getSupabaseEnvStatus } from "@/lib/env";

/**
 * Server-side entry point for the OAuth setup checklist.
 *
 * The caller's origin has to come from the request (proxy headers), and
 * `next/headers` cannot be imported from a client bundle — so the pages
 * compute the plan here and hand it down as plain data.
 *
 * Returns `null` in production and whenever Supabase is not configured;
 * `AuthConfigNotice` covers that case instead.
 */
export async function getOAuthRedirectPlan(): Promise<OAuthRedirectPlan | null> {
  if (process.env.NODE_ENV === "production") return null;

  const { env } = getSupabaseEnvStatus();

  if (!env) return null;

  const requestHeaders = await headers();

  const origin = appOriginFromRequestHeaders({
    host: requestHeaders.get("host"),
    forwardedHost: requestHeaders.get("x-forwarded-host"),
    forwardedProto: requestHeaders.get("x-forwarded-proto"),
    origin: requestHeaders.get("origin"),
  });

  return origin ? buildOAuthRedirectPlan(env.url, origin) : null;
}
