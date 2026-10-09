/**
 * Google Identity Services (GIS) loader + nonce helper.
 *
 * GIS renders Google's sign-in UI *inside our own page* and hands back an ID
 * token (a JWT) for the signed-in Google account. That token goes straight to
 * `supabase.auth.signInWithIdToken()`.
 *
 * The point, for this app: the browser never navigates to
 * `https://<project-ref>.supabase.co/auth/v1/authorize`, so Google's prompt is
 * keyed to *our* Authorized JavaScript origin and names our domain instead of
 * the Supabase project host. `lib/env.ts#getGoogleIdentityStatus` explains the
 * trade-off in full.
 *
 * Everything here is browser-only and deliberately dependency-free: one
 * `<script>` tag, loaded at most once per document, plus the SHA-256 nonce
 * dance Supabase expects (hashed value to Google, raw value to Supabase).
 */

/** Google's official GIS client library. */
export const GSI_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

/** The subset of `google.accounts.id` this app uses. */
export interface GoogleCredentialResponse {
  credential: string;
  select_by?: string;
}

export interface GoogleAccountsId {
  initialize(config: {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
    nonce?: string;
    auto_select?: boolean;
    cancel_on_tap_outside?: boolean;
    context?: "signin" | "signup" | "use";
    itp_support?: boolean;
    ux_mode?: "popup" | "redirect";
    use_fedcm_for_prompt?: boolean;
  }): void;

  renderButton(
    parent: HTMLElement,
    options: {
      type?: "standard" | "icon";
      theme?: "outline" | "filled_blue" | "filled_black";
      size?: "small" | "medium" | "large";
      text?: "signin_with" | "signup_with" | "continue_with" | "signin";
      shape?: "rectangular" | "pill" | "circle" | "square";
      logo_alignment?: "left" | "center";
      width?: number;
      locale?: string;
    },
  ): void;

  disableAutoSelect(): void;
  cancel(): void;
}

declare global {
  interface Window {
    google?: { accounts?: { id?: GoogleAccountsId } };
  }
}

let scriptPromise: Promise<GoogleAccountsId> | null = null;

/**
 * Inject `accounts.google.com/gsi/client` once and resolve with
 * `google.accounts.id`.
 *
 * Rejects on network failure, on an ad/tracker blocker removing the script,
 * and after `timeoutMs` — all three are normal in the wild, and the caller
 * falls back to the Supabase redirect flow rather than showing a dead button.
 */
export function loadGoogleIdentity(timeoutMs = 8000): Promise<GoogleAccountsId> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Google Identity Services is browser-only."));
  }

  const ready = window.google?.accounts?.id;
  if (ready) return Promise.resolve(ready);

  if (scriptPromise) return scriptPromise;

  scriptPromise = new Promise<GoogleAccountsId>((resolve, reject) => {
    const settle = (error?: Error) => {
      window.clearTimeout(timer);

      const api = window.google?.accounts?.id;

      if (api) {
        resolve(api);
        return;
      }

      // A failed load must not be cached: a retry (or a less hostile
      // network) should be able to succeed.
      scriptPromise = null;
      reject(
        error ??
          new Error(
            "Google Identity Services loaded but window.google.accounts.id is missing.",
          ),
      );
    };

    const timer = window.setTimeout(
      () =>
        settle(
          new Error(
            `Google Identity Services did not load within ${timeoutMs}ms ` +
              "(offline, or blocked by an extension / content blocker).",
          ),
        ),
      timeoutMs,
    );

    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${GSI_SCRIPT_SRC}"]`,
    );

    if (existing) {
      existing.addEventListener("load", () => settle(), { once: true });
      existing.addEventListener(
        "error",
        () => settle(new Error("Google Identity Services script failed to load.")),
        { once: true },
      );
      return;
    }

    const script = document.createElement("script");

    script.src = GSI_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.addEventListener("load", () => settle(), { once: true });
    script.addEventListener(
      "error",
      () => settle(new Error("Google Identity Services script failed to load.")),
      { once: true },
    );

    document.head.appendChild(script);
  });

  return scriptPromise;
}

export interface SignInNonce {
  /** Hashed (SHA-256, hex) — this is what Google is given. */
  hashed: string;
  /** Raw — this is what `signInWithIdToken` is given. */
  raw: string;
}

/**
 * Create the nonce pair Supabase expects.
 *
 * Supabase hashes the raw nonce and compares it with the `nonce` claim Google
 * embedded in the ID token, so the two sides must receive *different*
 * encodings of the same value.
 *
 * Returns `null` when `crypto.subtle` is unavailable — it only exists in a
 * secure context (https, or localhost). The caller then runs without a nonce,
 * which GIS and Supabase both allow; `signInWithIdToken` must omit it too,
 * because "passed nonce and nonce in id_token should either both exist or
 * both not exist".
 */
export async function createSignInNonce(): Promise<SignInNonce | null> {
  const subtle = globalThis.crypto?.subtle;

  if (!subtle || typeof globalThis.crypto?.getRandomValues !== "function") {
    return null;
  }

  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(32));
  const raw = btoa(String.fromCharCode(...bytes));

  const digest = await subtle.digest("SHA-256", new TextEncoder().encode(raw));

  const hashed = Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");

  return { hashed, raw };
}
