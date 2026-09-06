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
 *
 * IMPORTANT: Next.js loads environment files (`.env`, `.env.local`,
 * ...) from the frontend project folder when the dev server
 * STARTS. After editing them, fully restart `npm run dev`, or
 * rebuild before `npm run build && npm run start`.
 */

/** Base URL of the FastAPI backend, e.g. http://localhost:8000 */
export const API_URL: string =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ?? "http://localhost:8000";

/** Versioned API prefix used by the backend. */
export const API_BASE_URL: string = `${API_URL}/api/v1`;

function missingEnvMessage(name: string): string {
  return (
    `Missing ${name}.\n\n` +
    `Add it to the frontend environment file: frontend/.env or ` +
    `frontend/.env.local (copy frontend/.env.example), then FULLY restart ` +
    `the dev server - or rebuild before "npm run build && npm run start".\n\n` +
    `Find the values in the Supabase dashboard under ` +
    `Project Settings -> API (Project URL and the public "anon" key).`
  );
}

function requirePublicEnv(name: string): string {
  const value = process.env[name]?.trim();

  if (!value) {
    throw new Error(missingEnvMessage(name));
  }

  return value;
}

export interface SupabasePublicEnv {
  url: string;
  anonKey: string;
}

/**
 * Read both public Supabase values.
 * Returns `null` when either is missing or blank — never throws,
 * so server code (middleware, pages) can degrade gracefully.
 */
export function getSupabasePublicEnv(): SupabasePublicEnv | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();

  if (!url || !anonKey) {
    return null;
  }

  return { url, anonKey };
}

/** Public Supabase project URL. */
export function getSupabaseUrl(): string {
  return requirePublicEnv("NEXT_PUBLIC_SUPABASE_URL");
}

/** Public Supabase anon key (safe for the browser). */
export function getSupabaseAnonKey(): string {
  return requirePublicEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY");
}
