/**
 * Centralized frontend environment configuration.
 *
 * All public environment values are read here and imported
 * elsewhere — never scatter `process.env.NEXT_PUBLIC_*` reads
 * through the application.
 *
 * SECURITY: values prefixed NEXT_PUBLIC_ are inlined into the
 * browser bundle. Only low-privilege / public credentials may live
 * here (the publishable key, or the legacy anon key). Backend-only
 * secrets (SUPABASE_SERVICE_ROLE_KEY / sb_secret_*,
 * LANGFUSE_SECRET_KEY, QDRANT_API_KEY, OPENAI_API_KEY) must never
 * be added with a NEXT_PUBLIC_ prefix — the validation in
 * `getSupabaseEnvStatus()` rejects them instead of silently shipping a
 * bypass-RLS key to the client.
 *
 * IMPORTANT: Next.js loads environment files (`.env`, `.env.local`,
 * ...) from the frontend project folder when the dev server
 * STARTS, and bakes `NEXT_PUBLIC_*` values into the browser bundle at
 * that moment. After editing them you must see `Reload env: .env.local` in
 * the dev-server terminal — if you do not, restart it (Ctrl+C, `npm run
 * dev`). A production build needs a rebuild, because the values are frozen
 * into the bundle. Run `npm run doctor` to check what Next.js will see.
 */

import {
  cleanEnvValue,
  inspectSupabaseEnv,
  type SupabaseEnvIssue,
  type SupabaseKeyKind,
} from "@/lib/supabase-env";

/** Base URL of the FastAPI backend, e.g. http://localhost:8000 */
export const API_URL: string =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ?? "http://localhost:8000";

/** Versioned API prefix used by the backend. */
export const API_BASE_URL: string = `${API_URL}/api/v1`;

/** The file the developer should edit — the one Next.js actually reads. */
export const ENV_FILE_HINT = "frontend/.env.local (frontend/.env also works)";

/** The key env var name Supabase currently documents, then the legacy one. */
const KEY_VARS = ["NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY"] as const;

export interface SupabasePublicEnv {
  url: string;
  anonKey: string;
  /** Which key kind is in use; affects only error copy. */
  keyKind: SupabaseKeyKind;
}

export interface SupabaseEnvStatus {
  /** True when the values look usable (validated, not merely non-empty). */
  configured: boolean;
  env: SupabasePublicEnv | null;
  issues: SupabaseEnvIssue[];
}

/*
 * `NEXT_PUBLIC_*` reads MUST be static member expressions
 * (`process.env.NEXT_PUBLIC_X`). Next.js replaces those literal expressions
 * with their values when it builds the browser bundle; a dynamic lookup
 * (`process.env[name]`) is NOT inlined and resolves to `undefined` in the
 * browser - which is exactly how a correctly configured `.env.local` still
 * produced "Missing NEXT_PUBLIC_SUPABASE_URL" on click. So: read every
 * variable literally here once, then index the snapshot.
 */
const PUBLIC_ENV: Record<string, string | undefined> = {
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
};

function readEnv(name: string): string {
  return PUBLIC_ENV[name] ?? "";
}

/**
 * Inspect the public Supabase configuration without throwing.
 *
 * Server code (proxy, pages) uses this to degrade gracefully; the auth
 * forms use `issues` to explain exactly what is misconfigured.
 */
export function getSupabaseEnvStatus(): SupabaseEnvStatus {
  const url = readEnv("NEXT_PUBLIC_SUPABASE_URL");

  const keyVar = KEY_VARS.find((name) => cleanEnvValue(readEnv(name)) !== "");
  const key = keyVar ? readEnv(keyVar) : "";

  const { url: cleanUrl, key: cleanKey, keyKind, issues } = inspectSupabaseEnv({
    url,
    key,
    keyVar: keyVar ?? KEY_VARS[0],
  });

  if (issues.length > 0) {
    return { configured: false, env: null, issues };
  }

  return {
    configured: true,
    env: { url: cleanUrl, anonKey: cleanKey, keyKind },
    issues: [],
  };
}

function formatIssue(issue: SupabaseEnvIssue): string {
  return `  - ${issue.problem}\n    Fix: ${issue.fix}`;
}

function missingEnvMessage(name: string, issues: SupabaseEnvIssue[]): string {
  const details =
    issues.length > 0 ? `\n\n${issues.map(formatIssue).join("\n")}` : "";

  return (
    `Supabase sign-in is not configured for this build: ${name} is unusable.` +
    details +
    `\n\n1. Copy frontend/.env.example to ${ENV_FILE_HINT}` +
    `   (bash: cp / PowerShell: Copy-Item / cmd: copy)` +
    `\n2. Fill in NEXT_PUBLIC_SUPABASE_URL and` +
    ` NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY (or NEXT_PUBLIC_SUPABASE_ANON_KEY).` +
    `   Supabase dashboard -> Project Settings -> API Keys: the "Publishable key"` +
    ` is the browser-safe one. The "anon" key is its legacy equivalent.` +
    `\n3. Restart the dev server (Ctrl+C, then npm run dev) so the new values are` +
    `   compiled into the browser bundle. Turbopack prints "Reload env: .env.local"` +
    `   when it picks a change up on its own; if that line is missing, restart.` +
    `   A production build must be rebuilt ("npm run build && npm run start").` +
    `\n\nVerify with: npm run doctor` +
    `\n(Values in the repository ROOT .env are only read by docker-compose,` +
    ` never by "npm run dev" run from frontend/.)`
  );
}

/**
 * The validated public env, or a thrown error that says precisely what to
 * change. Single call site for client code (one throw, one message).
 */
export function requireSupabaseEnv(): SupabasePublicEnv {
  const status = getSupabaseEnvStatus();

  if (status.env && status.configured) {
    return status.env;
  }

  const first = status.issues[0];

  throw new Error(missingEnvMessage(first?.name ?? "NEXT_PUBLIC_SUPABASE_URL", status.issues));
}

/**
 * Read both public Supabase values.
 * Returns `null` when either is missing, blank or unusable — never throws,
 * so server code (proxy, pages) can degrade gracefully.
 */
export function getSupabasePublicEnv(): SupabasePublicEnv | null {
  return getSupabaseEnvStatus().env;
}

/*
 * Intentionally no `getSupabaseUrl()` / `getSupabaseAnonKey()` helpers:
 * the two values are only ever needed together, and passing one of them
 * around without the other is how mismatched project/key pairs get built.
 * Use `requireSupabaseEnv()` (client) or `getSupabasePublicEnv()` (server).
 */
