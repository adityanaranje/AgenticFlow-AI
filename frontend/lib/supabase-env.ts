/**
 * Parsing + validation for the two browser-facing Supabase settings.
 *
 * Shared by `lib/env.ts` (runtime reads for the app) and
 * `scripts/doctor.mjs`-adjacent code, so "what is wrong with my env" has a
 * single answer everywhere it is asked.
 *
 * Why this exists: a missing/blank value, a value copied with quotes, a
 * placeholder left over from `.env.example`, a key from a different project
 * and — the dangerous one — a *secret* key pasted into a `NEXT_PUBLIC_*`
 * variable all used to look identical in the browser ("Missing
 * NEXT_PUBLIC_SUPABASE_URL" or an opaque fetch error). Each now gets its own
 * diagnosis and fix.
 *
 * SECURITY: everything here runs on values that end up in the browser
 * bundle. Only low-privilege keys (publishable, or legacy anon) may be
 * accepted; secret / service_role keys are rejected with an explicit error.
 */

/** Browser-safe Supabase key: the publishable key, or the legacy anon key. */
export type SupabaseKeyKind = "publishable" | "anon";

export interface SupabaseEnvIssue {
  /** Environment variable the problem belongs to. */
  name: string;
  /** Machine-readable reason, for tests and targeted UI copy. */
  code:
    | "missing"
    | "placeholder"
    | "quoted"
    | "invalid-url"
    | "secret-key"
    | "short-key";
  /** Human-readable diagnosis (one sentence). */
  problem: string;
  /** What to do about it (imperative, specific). */
  fix: string;
}

export interface SupabaseEnvCandidate {
  url: string;
  key: string;
  /** The key env var the value was read from (`NEXT_PUBLIC_...`). */
  keyVar: string;
}

/** Values copied from `.env.example` that are not real credentials. */
const PLACEHOLDER_RE = /^(?:<|\{|\[|\.\.\.$)|your[-_]|example|changeme|replace[-_]?me|todo|fixme|^x{4,}$|^0+$|^_+$/i;

/** Leading/trailing quote the copy-paste tools like to add. */
const QUOTED_RE = /^(['"`])([\s\S]*)\1$/;

/**
 * Clean a raw env value: strip an accidental BOM, surrounding quotes and
 * trailing whitespace. Supabase project URLs may be pasted with a trailing
 * slash, which produces `//auth/v1/...` requests if left alone.
 */
export function cleanEnvValue(raw: string | undefined | null): string {
  if (!raw) return "";

  let value = raw.replace(/^\uFEFF/, "").trim();

  const quoted = QUOTED_RE.exec(value);
  if (quoted) value = quoted[2]!.trim();

  return value;
}

/**
 * Accept `https://xyz.supabase.co`, `xyz.supabase.co/`, and
 * `"https://xyz.supabase.co/"` alike, and return a scheme-ful,
 * slash-free URL. Returns `""` when nothing usable remains.
 */
export function normalizeSupabaseUrl(raw: string | undefined | null): string {
  let value = cleanEnvValue(raw);

  if (!value) return "";

  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(value)) {
    value = `https://${value}`;
  }

  return value.replace(/\/+$/, "");
}

/** Decode a legacy JWT key's payload. `null` for opaque / malformed keys. */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split(".");

  if (parts.length !== 3 || !parts[1]) return null;

  // `atob` exists in the browser, in Node 16+ and in the Edge runtime, which
  // covers every place this module is loaded. No fallback needed.
  if (typeof atob !== "function") return null;

  try {
    const base64 = parts[1]
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(parts[1].length / 4) * 4, "=");

    return JSON.parse(atob(base64)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Identify a Supabase key. Returns the Postgres role it presents as
 * (`anon` / `authenticated` / `service_role`) or `null` when unknown.
 */
export function detectSupabaseKeyKind(key: string): {
  /** `sb_publishable_` / legacy `anon` / `sb_secret_` / `service_role`. */
  kind: "publishable" | "anon" | "secret" | "service-role" | "unknown";
  role: string | null;
} {
  if (key.startsWith("sb_publishable_")) return { kind: "publishable", role: "anon" };
  if (key.startsWith("sb_secret_")) return { kind: "secret", role: "service_role" };

  const payload = decodeJwtPayload(key);
  const role = typeof payload?.role === "string" ? payload.role : null;

  if (role === "service_role") return { kind: "service-role", role };
  if (role === "anon") return { kind: "anon", role };

  return { kind: "unknown", role };
}

/**
 * Validate one (url, key) pair. `issues` is empty when the pair looks
 * usable; `url`/`key` are returned cleaned and normalized.
 */
export function inspectSupabaseEnv({
  url,
  key,
  keyVar,
}: SupabaseEnvCandidate): {
  url: string;
  key: string;
  keyKind: SupabaseKeyKind;
  issues: SupabaseEnvIssue[];
} {
  const issues: SupabaseEnvIssue[] = [];

  const rawUrl = (url ?? "").replace(/^\uFEFF/, "").trim();
  const rawKey = (key ?? "").replace(/^\uFEFF/, "").trim();

  const cleanUrl = normalizeSupabaseUrl(rawUrl);
  const cleanKey = cleanEnvValue(rawKey);

  const urlName = "NEXT_PUBLIC_SUPABASE_URL";
  const keyName = keyVar || "NEXT_PUBLIC_SUPABASE_ANON_KEY";

  if (!rawUrl) {
    issues.push({
      name: urlName,
      code: "missing",
      problem: `${urlName} is empty or not loaded.`,
      fix: `Set ${urlName} to your project URL (Supabase dashboard -> Project Settings -> API Keys, or the "Connect" dialog), then restart the dev server.`,
    });
  } else if (PLACEHOLDER_RE.test(rawUrl)) {
    issues.push({
      name: urlName,
      code: "placeholder",
      problem: `${urlName} still holds a placeholder value ("${rawUrl.slice(0, 40)}").`,
      fix: `Replace it with the real project URL, e.g. https://<project-ref>.supabase.co.`,
    });
  } else if (QUOTED_RE.test(rawUrl)) {
    issues.push({
      name: urlName,
      code: "quoted",
      problem: `${urlName} is wrapped in quotes.`,
      fix: `Remove the quotes: ${urlName}=https://<project-ref>.supabase.co`,
    });
  } else {
    try {
      const parsed = new URL(cleanUrl);

      if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
        throw new Error("scheme");
      }
      if (!parsed.hostname.includes(".")) {
        throw new Error("hostname");
      }
    } catch {
      issues.push({
        name: urlName,
        code: "invalid-url",
        problem: `${urlName} is not a valid URL ("${rawUrl.slice(0, 60)}").`,
        fix: `Write it as a full URL including the scheme, e.g. https://<project-ref>.supabase.co (no path, no trailing slash).`,
      });
    }
  }

  if (!rawKey) {
    issues.push({
      name: keyName,
      code: "missing",
      problem: `${keyName} is empty or not loaded.`,
      fix:
        `Set ${keyName} to your project's publishable key (sb_publishable_...), or use ` +
        `NEXT_PUBLIC_SUPABASE_ANON_KEY if your project still has the legacy anon key.`,
    });
  } else {
    const detected = detectSupabaseKeyKind(cleanKey);

    if (detected.kind === "secret" || detected.kind === "service-role") {
      issues.push({
        name: keyName,
        code: "secret-key",
        problem: `${keyName} contains a SECRET Supabase key (it presents as the service_role Postgres role). It bypasses Row Level Security and must never reach the browser bundle.`,
        fix: `Use the publishable key instead. Rotate the secret key in the Supabase dashboard if it was ever committed, pasted into a browser tool or shared in a chat.`,
      });
    } else if (PLACEHOLDER_RE.test(cleanKey)) {
      issues.push({
        name: keyName,
        code: "placeholder",
        problem: `${keyName} still holds a placeholder value ("${cleanKey.slice(0, 40)}").`,
        fix: `Paste the real publishable key from Project Settings -> API Keys.`,
      });
    } else if (cleanKey.length < 32) {
      issues.push({
        name: keyName,
        code: "short-key",
        problem: `${keyName} looks truncated (${cleanKey.length} characters).`,
        fix: `Re-copy the whole key — publishable keys are ~40+ characters, legacy anon JWTs ~250.`,
      });
    }
  }

  const keyKind: SupabaseKeyKind = cleanKey.startsWith("sb_publishable_")
    ? "publishable"
    : "anon";

  return { url: cleanUrl, key: cleanKey, keyKind, issues };
}
