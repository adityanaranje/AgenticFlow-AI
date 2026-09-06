/**
 * Centralized frontend environment configuration.
 *
 * All public environment values are read here and imported
 * elsewhere — never scatter `process.env.NEXT_PUBLIC_*` reads
 * through the application.
 *
 * SECURITY: values prefixed NEXT_PUBLIC_ are inlined into the
 * browser bundle. Only public / anonymous credentials may live
 * here. Backend-only secrets (SUPABASE_SERVICE_ROLE_KEY,
 * LANGFUSE_SECRET_KEY, QDRANT_API_KEY, OPENAI_API_KEY) must never
 * be added with a NEXT_PUBLIC_ prefix.
 */

/** Base URL of the FastAPI backend, e.g. http://localhost:8000 */
export const API_URL: string =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ?? "http://localhost:8000";

/** Versioned API prefix used by the backend. */
export const API_BASE_URL: string = `${API_URL}/api/v1`;

function requirePublicEnv(name: string): string {
  const value = process.env[name];

  if (!value) {
    throw new Error(
      `Missing ${name}. Copy frontend/.env.example to frontend/.env.local ` +
        "and set the Supabase project values.",
    );
  }

  return value;
}

/** Public Supabase project URL. */
export function getSupabaseUrl(): string {
  return requirePublicEnv("NEXT_PUBLIC_SUPABASE_URL");
}

/** Public Supabase anon key (safe for the browser). */
export function getSupabaseAnonKey(): string {
  return requirePublicEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY");
}
