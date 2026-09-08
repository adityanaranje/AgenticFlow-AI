#!/usr/bin/env node
/**
 * AgentFlow AI — frontend environment doctor.
 *
 *   npm run doctor              validate what Next.js will actually load
 *   npm run doctor -- --offline skip the live Supabase reachability check
 *   npm run doctor -- --copy    create frontend/.env.local from the example
 *   npm run doctor -- --mode=production   validate for `next build` instead
 *
 * Why this exists: `NEXT_PUBLIC_*` values are baked into the browser bundle
 * when the dev server STARTS, from the .env files inside `frontend/`. That
 * single fact causes a whole family of "sign-in is broken" reports:
 *
 *   - values placed in the repository ROOT .env (only docker-compose reads it)
 *   - .env edited but the dev server never restarted
 *   - an empty NEXT_PUBLIC_* variable exported in the shell, which WINS over
 *     the file (Next.js stops at the first definition it finds)
 *   - a file written by PowerShell `echo ... > .env.local` (UTF-16, unparsable)
 *   - quotes, trailing slashes, placeholders left from .env.example
 *   - a Supabase SECRET key pasted where the publishable/anon key belongs
 *   - a key from a different Supabase project than the URL
 *
 * The browser cannot tell those apart; this script can. Zero dependencies,
 * no build step, and it never prints a key in full.
 */

import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = resolve(FRONTEND_DIR, "..");

const URL_VAR = "NEXT_PUBLIC_SUPABASE_URL";
const KEY_VARS = ["NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY"];
const API_URL_VAR = "NEXT_PUBLIC_API_URL";

const argv = process.argv.slice(2);
const flags = new Set(argv.filter((a) => a.startsWith("--")).map((a) => a.split("=")[0]));
const modeFromArg = argv.find((a) => a.startsWith("--mode="))?.split("=")[1];
const MODE = modeFromArg ?? (process.env.NODE_ENV === "test" ? "test" : "development");
const OFFLINE = flags.has("--offline");
const COPY = flags.has("--copy");

const C = process.stdout.hasColors?.("stdout") === false ? noColor() : color();

function color() {
  const wrap = (open, close) => (s) => `\u001b[${open}m${s}\u001b[${close}m`;
  return {
    bold: wrap(1, 22),
    dim: wrap(2, 22),
    red: wrap(31, 39),
    green: wrap(32, 39),
    yellow: wrap(33, 39),
    cyan: wrap(36, 39),
  };
}

function noColor() {
  const id = (s) => s;
  return { bold: id, dim: id, red: id, green: id, yellow: id, cyan: id };
}

/** Files Next.js loads, highest priority first (see its env docs). */
function envFileCandidates(mode) {
  return [
    `.env.${mode}.local`,
    mode !== "test" && `.env.local`,
    `.env.${mode}`,
    `.env`,
  ].filter(Boolean);
}

/**
 * Parse a dotenv file the way Next.js does (dotenv@16 semantics), keeping
 * line numbers so findings can be pointed at.
 */
function parseEnvFile(text) {
  const entries = new Map();
  const LINE_RE =
    /(?:^|^)\s*(?:export\s+)?([\w.-]+)(?:\s*=\s*?|:\s+?)(\s*'(?:\\'|[^'])*'|\s*"(?:\\"|[^"])*"|\s*`(?:\\`|[^`])*`|[^#\r\n]+)?\s*(?:#.*)?(?:$|$)/gm;

  const normalized = text.replace(/\r\n?/gm, "\n");
  const offsets = [];
  let index = 0;
  for (const line of normalized.split("\n")) {
    offsets.push(index);
    index += line.length + 1;
  }

  let match;
  while ((match = LINE_RE.exec(normalized)) !== null) {
    const raw = match[2] ?? "";
    const quoted = /^(['"`])[\s\S]*\1$/.test(raw.trim());
    const value = raw.trim().replace(/^(['"`])([\s\S]*)\1$/gm, "$2");
    const name = match[1];

    const line = offsets.findIndex(
      (start, i) => match.index >= start && (i === offsets.length - 1 || match.index < offsets[i + 1]),
    );

    entries.set(name, {
      value,
      quoted,
      raw: raw.trim(),
      line: line + 1,
    });
  }

  return { entries, lineCount: offsets.length };
}

function readFrontendEnvFiles(mode) {
  const files = [];

  for (const name of envFileCandidates(mode)) {
    const path = join(FRONTEND_DIR, name);

    if (!existsSync(path)) continue;
    const stat = statSync(path);
    if (!stat.isFile()) continue;

    const buffer = readFileSync(path);
    const issues = [];

    if (buffer[0] === 0xff && buffer[1] === 0xfe) {
      issues.push("UTF-16LE encoding");
    } else if (buffer[0] === 0xfe && buffer[1] === 0xff) {
      issues.push("UTF-16BE encoding");
    } else if (buffer.includes(0x00)) {
      issues.push("contains NUL bytes (looks like UTF-16)");
    }

    const startsWithBom = buffer[0] === 0xef && buffer[1] === 0xbb && buffer[2] === 0xbf;
    const text = buffer.toString("utf8").replace(/^/, "");

    files.push({
      name,
      path,
      text,
      buffer,
      encodingIssues: issues,
      hasUtf8Bom: startsWithBom,
      parsed: parseEnvFile(text),
      mtime: stat.mtime,
    });
  }

  return files;
}

/** value -> file that defines it, in Next.js precedence order. */
function resolveValue(name, files) {
  for (const file of files) {
    const entry = file.parsed.entries.get(name);
    if (entry) return { ...entry, file: file.name };
  }
  return null;
}

/**
 * The same variable as seen by Next.js, plus a "shadowedBy" hint: a blank
 * `VAR=` in a higher-priority file silently hides a good value in a lower one.
 */
function resolveEffectiveValue(name, files) {
  const found = resolveValue(name, files);

  if (found && found.value.trim() === "") {
    const better = files
      .filter((file) => file.name !== found.file)
      .map((file) => ({ file: file.name, ...file.parsed.entries.get(name) }))
      .find((entry) => entry.value && entry.value.trim() !== "");

    if (better) return { ...found, shadowedBy: better };
  }

  return found;
}

function mask(value) {
  if (!value) return "(empty)";
  if (value.length <= 12) return `${"*".repeat(value.length)} (${value.length} chars)`;
  return `${value.slice(0, 6)}${"*".repeat(6)}${value.slice(-4)} (${value.length} chars)`;
}

function looksLikePlaceholder(value) {
  return (
    /^(?:<|\{|\[|\.\.\.$)|your[-_]|example|changeme|replace[-_]?me|todo|fixme|^x{4,}$|^0+$|^_+$/i.test(
      value ?? "",
    ) ||
    value.trim() === ""
  );
}

function decodeJwtPayload(token) {
  const parts = token.split(".");
  if (parts.length !== 3) return null;

  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(Buffer.from(base64, "base64").toString("utf8"));
  } catch {
    return null;
  }
}

const findings = { errors: [], warnings: [], infos: [] };
const error = (title, ...lines) => findings.errors.push({ title, lines });
const warn = (title, ...lines) => findings.warnings.push({ title, lines });
const info = (title, ...lines) => findings.infos.push({ title, lines });

// ---------------------------------------------------------------------------

function checkShellShadowing(name, files) {
  const fromShell = process.env[name];

  if (fromShell === undefined) return;

  const fromFile = files
    .map((file) => {
      const entry = file.parsed.entries.get(name);
      return entry ? { file: file.name, ...entry } : null;
    })
    .filter(Boolean)
    .at(0);

  if (!fromFile) {
    info(`${name} comes from your shell`, `value: ${describe(fromShell)}`);
    return;
  }

  if (fromShell === "") {
    error(
      `${name} is set to an EMPTY value in your shell, which hides the file`,
      "Next.js reads process.env first and stops at the first definition it finds —",
      fromFile
        ? `an empty shell value therefore overrides (and silently disables) the value in frontend/${fromFile.file}:${fromFile.line}.`
        : "and no frontend/.env* file defines it either, so the app sees an empty value.",
      "Fix (PowerShell): Remove-Item Env:NEXT_PUBLIC_SUPABASE_URL",
      "Fix (cmd):        set NEXT_PUBLIC_SUPABASE_URL=",
      "Fix (bash/zsh):   unset NEXT_PUBLIC_SUPABASE_URL",
      "Then restart `npm run dev` from a fresh terminal.",
    );
    return;
  }

  if (fromShell.trim() !== fromFile.value.trim()) {
    warn(
      `${name} is defined BOTH in your shell and in frontend/${fromFile.file}`,
      `the shell value wins: ${describe(fromShell)}`,
      `the file value is ignored: ${describe(fromFile.value)}`,
    );
  }
}

function describe(value) {
  return value.length > 60 ? `${value.slice(0, 60)}… (${value.length} chars)` : value || "(empty)";
}

function checkUrl(files) {
  const found = resolveEffectiveValue(URL_VAR, files);

  if (!found || found.value.trim() === "") {
    error(
      `${URL_VAR} is not set anywhere Next.js will read`,
      found
        ? `it is declared but empty in frontend/${found.file} (line ${found.line})` +
          (found.shadowedBy
            ? ` — and that blank line wins over the value in frontend/${found.shadowedBy.file}:${found.shadowedBy.line}`
            : "")
        : "no frontend/.env* file defines it",
      "",
      "1. Create the file:  cp frontend/.env.example frontend/.env.local",
      "                    PowerShell: Copy-Item frontend/.env.example frontend/.env.local",
      "2. Set the value to your project URL, e.g. NEXT_PUBLIC_SUPABASE_URL=https://abcdefghijklmn.supabase.co",
      "   (Supabase dashboard → Project Settings → API Keys, or the “Connect” dialog)",
      "3. FULLY restart the dev server: Ctrl+C, then npm run dev.",
      "   NEXT_PUBLIC_* values are inlined when the server starts; editing the file alone does nothing.",
    );
    return null;
  }

  const value = found.value.trim();
  const where = `frontend/${found.file}:${found.line}`;

  if (found.quoted) {
    warn(`${URL_VAR} is wrapped in quotes`, `${where} → ${value}`, "Quotes are stripped by Next.js, but they break copy-paste round-trips; prefer the bare value.");
  }

  if (looksLikePlaceholder(value)) {
    error(`${URL_VAR} still holds a placeholder`, `${where} → ${value}`, "Replace it with your real project URL.");
    return null;
  }

  const candidate = /^[a-z][a-z0-9+.-]*:\/\//i.test(value) ? value : `https://${value}`;

  let url;
  try {
    url = new URL(candidate.replace(/\/+$/, ""));
  } catch {
    error(`${URL_VAR} is not a valid URL`, `${where} → ${value}`, "Expected https://<project-ref>.supabase.co (or your self-hosted URL), with no path.");
    return null;
  }

  if (!/^https?:$/.test(url.protocol)) {
    error(`${URL_VAR} must use http(s)`, `${where} → ${value}`);
    return null;
  }

  if (url.pathname !== "/" && url.pathname !== "") {
    warn(`${URL_VAR} contains a path`, `${where} → ${value}`, "Only the origin belongs here (Supabase appends /auth/v1, /rest/v1, ... itself).");
  }

  if (url.protocol === "http:" && !["localhost", "127.0.0.1"].includes(url.hostname)) {
    warn(`${URL_VAR} uses plain http`, `${where} → ${value}`, "Use https for hosted Supabase projects, otherwise browsers may block the request as mixed content.");
  }

  // Hosted projects use a 20-character ref; a very short or malformed label
  // almost always means a truncated paste or a value that is not a URL at all.
  if (url.hostname.includes("supabase") && (url.hostname.length < 20 || /\s|:|%|\.co\./.test(url.hostname))) {
    warn(`${URL_VAR} host does not look like a Supabase project URL`, `${where} → ${url.host}`, "Expected <project-ref>.supabase.co (the ref is 20 characters) — check for a truncated paste.");
  }

  return { url: url.origin, ref: url.hostname.split(".")[0] };
}

function checkKey(files) {
  const varName = KEY_VARS.find((name) => {
    const found = resolveValue(name, files);
    return found && found.value.trim() !== "";
  });

  const found = varName ? resolveValue(varName, files) : null;

  if (!found || found.value.trim() === "") {
    error(
      `No Supabase browser key found (${KEY_VARS.join(" or ")})`,
      "Set the project's publishable key (sb_publishable_...), or the legacy anon key while your project still has one:",
      "  Supabase dashboard → Project Settings → API Keys → Publishable key",
      `in ${ENV_FILE_HINT}, then fully restart the dev server.`,
    );
    return null;
  }

  const value = found.value.trim();
  const where = `frontend/${found.file}:${found.line}`;
  const isSecret = value.startsWith("sb_secret_");
  const payload = decodeJwtPayload(value);
  const isServiceRole = payload?.role === "service_role";

  if (isSecret || isServiceRole) {
    error(
      `${varName} contains a SECRET key (${isSecret ? "sb_secret_..." : "service_role JWT"})`,
      `${where} → ${mask(value)}`,
      "A NEXT_PUBLIC_* variable is compiled into the JavaScript you ship to every browser.",
      "A secret key bypasses Row Level Security — anyone who loads the page can read and write all tenant data.",
      "Supabase also returns HTTP 401 for secret keys used from a browser, so sign-in fails at the same time.",
      "",
      "1. Replace the value with the PUBLISHABLE key (or legacy anon key).",
      "2. Rotate the leaked secret in the dashboard (Project Settings → API Keys).",
      "3. Keep the secret key in backend/.env as SUPABASE_SERVICE_ROLE_KEY (backend only).",
    );
    return null;
  }

  if (looksLikePlaceholder(value)) {
    error(`${varName} still holds a placeholder`, `${where} → ${describe(value)}`, "Paste the real key.");
    return null;
  }

  if (found.quoted) {
    warn(`${varName} is wrapped in quotes`, `${where}`, "Prefer the bare value to keep copy-paste mistakes visible.");
  }

  if (value.length < 32) {
    error(`${varName} looks truncated (${value.length} characters)`, `${where} → ${mask(value)}`, "Publishable keys are ~40 characters; legacy anon JWTs ~250. Re-copy the whole value.");
    return null;
  }

  if (!value.startsWith("sb_publishable_") && !payload) {
    warn(
      `${varName} is neither a publishable key nor a decodable JWT`,
      `${where} → ${mask(value)}`,
      "Check you did not paste a project ref, a database password or the JWT secret.",
    );
  }

  if (varName === KEY_VARS[1]) {
    info(`${varName} is the legacy variable name`, "Supabase now labels this key “Publishable”. NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY is read as well and is the forward-compatible name.");
  }

  return { value, varName: varName ?? KEY_VARS[1], kind: value.startsWith("sb_publishable_") ? "publishable" : "anon" };
}

const ENV_FILE_HINT = "frontend/.env.local (or frontend/.env)";

function checkKeyMatchesProject(urlInfo, key) {
  if (!urlInfo || !key) return;

  const payload = decodeJwtPayload(key.value);
  const iss = typeof payload?.iss === "string" ? payload.iss : null;

  if (!iss) return;

  let refFromIss = null;
  try {
    refFromIss = new URL(iss).hostname.split(".")[0];
  } catch {
    refFromIss = iss.includes(".") ? iss.split(".")[0] : iss;
  }

  if (refFromIss && refFromIss !== urlInfo.ref) {
    error(
      "The anon key belongs to a different Supabase project than the URL",
      `${URL_VAR} → project ref “${urlInfo.ref}”`,
      `${key.varName} → issued for “${refFromIss}” (its iss claim)`,
      "Supabase rejects that combination, which shows up as a sign-in failure. Use the key from the same project.",
    );
  }
}

async function checkRootEnv(files) {
  if (files.length > 0) return;

  const rootEnv = join(REPO_ROOT, ".env");
  if (!existsSync(rootEnv)) return;

  const { entries } = parseEnvFile(readFileSync(rootEnv, "utf8"));

  const hasPublic = [...entries.keys()].some((k) => k.startsWith("NEXT_PUBLIC_"));

  if (hasPublic) {
    error(
      "NEXT_PUBLIC_* values were placed in the repository ROOT .env",
      "checked file: .env in the repository root",
      "That file is only read by docker-compose. `npm run dev`, run from frontend/, loads",
      "frontend/.env* and never looks at the parent folder.",
      "Move the NEXT_PUBLIC_* lines into frontend/.env.local (then restart the dev server),",
      "or run the whole stack with `docker compose up --build`, which does read the root file.",
    );
  }
}

async function liveCheck(urlInfo, key) {
  if (!urlInfo || !key) return;
  if (OFFLINE) {
    info("Live Supabase check skipped (--offline)");
    return;
  }

  const endpoint = `${urlInfo.url}/auth/v1/settings`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(endpoint, {
      headers: { apikey: key.value, Authorization: `Bearer ${key.value}` },
      signal: controller.signal,
    });

    if (response.ok) {
      findings.checkedOk = `Live check: ${endpoint} → HTTP ${response.status} — URL and key match a real project.`;
      return;
    }

    if (response.status === 400 || response.status === 401 || response.status === 403) {
      error(
        `Supabase rejected the key (HTTP ${response.status})`,
        `GET ${endpoint}`,
        `apikey: ${mask(key.value)} (${key.kind} key from ${key.varName})`,
        "Usually the key is from another project, was rotated, or legacy anon keys are disabled for the project.",
        "Copy the current publishable key from Project Settings → API Keys and restart the dev server.",
      );
      return;
    }

    findings.checkedWarn = `Live check returned HTTP ${response.status} from ${endpoint} — the project answered, so the URL is reachable.`;
  } catch (cause) {
    const code =
      cause instanceof Error && cause.cause && typeof cause.cause === "object"
        ? String(cause.cause.code ?? cause.cause.errno ?? "")
        : "";

    const hints = {
      ENOTFOUND:
        "No DNS record for that host — the project ref in the URL does not exist (typo, or the project was deleted).",
      EAI_AGAIN: "DNS lookup failed/timed out from this network.",
      ECONNREFUSED: "Nothing is listening on that host/port — for a self-hosted Supabase, check the port.",
      ECONNRESET: "The connection was reset — a proxy or VPN often blocks *.supabase.co.",
      ETIMEDOUT: "The connection timed out — check VPN/proxy settings.",
      AbortError: "Timed out after 15s — the host did not answer.",
    };

    error(
      "The Supabase URL is not reachable from this machine",
      `GET ${endpoint}`,
      `cause: ${code || (cause instanceof Error ? cause.message : String(cause))}`,
      hints[code] ??
        "Check the project ref spelling, your network/VPN, and that the project is not paused (Supabase pauses inactive free projects).",
    );
  } finally {
    clearTimeout(timer);
  }
}

function printSection(title, items, marker, colorFn) {
  if (items.length === 0) return;

  console.log(`\n${colorFn(title)}`);

  for (const item of items) {
    console.log(`  ${marker} ${C.bold(item.title)}`);
    for (const line of item.lines) {
      console.log(line === "" ? "" : `      ${C.dim(line)}`);
    }
  }
}

// ---------------------------------------------------------------------------

async function main() {
  console.log(`\n${C.bold("AgentFlow AI — frontend environment doctor")}`);
  console.log(C.dim(`mode: ${MODE} · project dir: ${FRONTEND_DIR}\n`));

  if (COPY) {
    const target = join(FRONTEND_DIR, ".env.local");
    const template = join(FRONTEND_DIR, ".env.example");

    if (existsSync(target)) {
      info("frontend/.env.local already exists — left untouched");
    } else {
      writeFileSync(target, readFileSync(template, "utf8"), { encoding: "utf8" });
      console.log(`  ${C.green("✔")} created frontend/.env.local from .env.example — fill in the two Supabase values`);
    }
  }

  const files = readFrontendEnvFiles(MODE);

  if (files.length === 0) {
    error(
      `No env file found in frontend/ (looked for: ${envFileCandidates(MODE).join(", ")})`,
      `Only frontend/.env.example exists, and example files are never loaded.`,
      "Fix:  npm run doctor -- --copy        (or cp frontend/.env.example frontend/.env.local)",
      "      then fill in the values and start the dev server from that state.",
    );
  }

  for (const file of files) {
    if (file.encodingIssues.length > 0) {
      error(
        `frontend/${file.name} is not plain UTF-8 (${file.encodingIssues.join(", ")})`,
        "Next.js silently loads no variables from such a file — the usual cause is PowerShell:",
        "  echo NEXT_PUBLIC_SUPABASE_URL=... > .env.local   # writes UTF-16",
        "Rewrite it as UTF-8 without BOM, e.g. open it in an editor and save,",
        "or:  Get-Content .env.local | Set-Content -Encoding utf8NoBOM .env.local",
      );
    } else if (file.hasUtf8Bom) {
      warn(`frontend/${file.name} starts with a UTF-8 BOM`, "The first variable name may be read as “\uFEFFNEXT_PUBLIC_...”. Save the file as “UTF-8 without BOM”.");
    }

    info(
      `frontend/${file.name}`,
      `${file.parsed.entries.size} variable(s) · last modified ${file.mtime.toISOString()}`,
      file.parsed.entries.has("NEXT_PUBLIC_SUPABASE_URL")
        ? `defines ${URL_VAR} (line ${file.parsed.entries.get("NEXT_PUBLIC_SUPABASE_URL").line})`
        : `does not define ${URL_VAR}`,
    );
  }

  const filesHaveEnv = files.length > 0;

  if (filesHaveEnv) {
    checkShellShadowing(URL_VAR, files);
    for (const name of KEY_VARS) checkShellShadowing(name, files);
  }

  await checkRootEnv(files);

  const urlInfo = checkUrl(files);
  const key = checkKey(files);

  checkKeyMatchesProject(urlInfo, key);
  await liveCheck(urlInfo, key);

  const apiUrl = resolveValue(API_URL_VAR, files);
  if (!apiUrl) {
    info(`${API_URL_VAR} not set`, `frontend code will use the default http://localhost:8000 (see lib/env.ts).`);
  }

  printSection("Problems", findings.errors, `${C.red("✖")}`, C.red);
  printSection("Worth a look", findings.warnings, `${C.yellow("▲")}`, C.yellow);
  printSection("Details", findings.infos, `${C.cyan("·")}`, C.dim);

  if (findings.checkedOk) console.log(`\n  ${C.green("✔")} ${findings.checkedOk}`);
  if (findings.checkedWarn) console.log(`\n  ${C.yellow("▲")} ${findings.checkedWarn}`);

  if (findings.errors.length === 0 && findings.warnings.length === 0) {
    console.log(
      `\n${C.green("✔ Frontend environment looks good.")} ${C.dim(
        "Remember: after editing an env file, restart the dev server (Ctrl+C, npm run dev).",
      )}\n`,
    );
    process.exitCode = 0;
    return;
  }

  if (findings.errors.length === 0) {
    console.log(`\n${C.yellow("▲ No blocking problems — only the notes above.")}\n`);
    process.exitCode = 0;
    return;
  }

  console.log(
    `\n${C.red(`✖ ${findings.errors.length} blocking problem(s).`)} Fix them, restart the dev server, and sign-in will work.\n`,
  );
  process.exitCode = 1;
}

await main();
