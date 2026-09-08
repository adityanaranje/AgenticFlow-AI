import type { NextConfig } from "next";

/*
 * Startup environment check.
 *
 * `NEXT_PUBLIC_*` values are read once, when this process starts, and then
 * inlined into the browser bundle. A missing value therefore does not produce
 * a startup error — it produces a broken sign-in button much later, in the
 * browser. Print the problem where it can actually be fixed: in the terminal,
 * next to the "ready on http://localhost:3000" line.
 *
 * This is a warning, not a hard failure: the app must still boot (docs pages,
 * the marketing page, `/health`-style checks) and the auth pages show the same
 * guidance inline via `components/auth/AuthConfigNotice.tsx`.
 *
 * NOTE: Next.js loads `frontend/.env*` (not the repository root `.env`)
 * before evaluating this file, so these reads reflect what the browser bundle
 * will get. Verify any value with `npm run doctor`.
 */
function checkSupabaseEnv(): string[] {
  const problems: string[] = [];

  const url = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").trim();
  const key =
    (process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "")
      .trim();

  if (!url) {
    problems.push("NEXT_PUBLIC_SUPABASE_URL is empty or not loaded.");
  } else if (!/^https?:\/\//i.test(url)) {
    problems.push(`NEXT_PUBLIC_SUPABASE_URL is missing a scheme ("${url}").`);
  }

  if (!key) {
    problems.push(
      "No Supabase browser key loaded (set NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY or the legacy NEXT_PUBLIC_SUPABASE_ANON_KEY).",
    );
  } else if (key.startsWith("sb_secret_")) {
    problems.push(
      "A SECRET Supabase key (sb_secret_...) is configured for the browser. It would be shipped in the public bundle and Supabase rejects it from browsers — use the publishable key.",
    );
  }

  return problems;
}

const supabaseProblems = checkSupabaseEnv();

if (supabaseProblems.length > 0) {
  const width = 76;
  const line = "-".repeat(width);

  const wrap = (text: string, indent = "", contIndent = indent): string[] => {
    const lines: string[] = [];
    let current = indent;

    for (const word of text.split(/\s+/)) {
      if (current !== indent && current.length + word.length + 1 > width - 4) {
        lines.push(current);
        current = contIndent;
      }
      current += (current === indent || current === contIndent ? "" : " ") + word;
    }

    lines.push(current);

    return lines;
  };

  const pad = (text: string) => `| ${text.padEnd(width - 3)}`;

  console.warn(
    [
      "",
      line,
      ...wrap("Supabase sign-in will not work in this build:").map(pad),
      ...supabaseProblems.flatMap((problem) => wrap(problem, "  - ", "    ")).map(pad),
      pad(""),
      pad("1. Copy frontend/.env.example to frontend/.env.local and fill in"),
      pad("   NEXT_PUBLIC_SUPABASE_URL and the publishable (or legacy anon) key."),
      pad("2. Restart the dev server (Ctrl+C, then npm run dev) — NEXT_PUBLIC_*"),
      pad("   values are baked into the browser bundle when it starts."),
      pad("3. npm run doctor  validates the files and calls Supabase to confirm."),
      line,
      "",
    ].join("\n"),
  );
}

const nextConfig: NextConfig = {
  // Standalone output lets the Docker image run `node server.js`
  // without shipping node_modules (see frontend/Dockerfile).
  output: "standalone",
};

export default nextConfig;
