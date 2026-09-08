import { createBrowserClient } from "@supabase/ssr";

import { requireSupabaseEnv } from "@/lib/env";

/**
 * Browser Supabase client.
 *
 * `requireSupabaseEnv()` throws a self-explaining error when the public
 * Supabase variables are missing/blank/invalid (or when a secret key was
 * pasted in) — that error is rendered as a setup notice by the auth forms,
 * not as a failed sign-in.
 */
export function createClient() {
  const { url, anonKey } = requireSupabaseEnv();

  return createBrowserClient(url, anonKey);
}
