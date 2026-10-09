"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CircleAlert, Loader2 } from "lucide-react";

import GoogleRedirectButton from "@/components/auth/GoogleRedirectButton";
import { describeAuthError, describeIdTokenError } from "@/lib/auth-errors";
import { getGoogleIdentityStatus, getSupabaseEnvStatus } from "@/lib/env";
import {
  createSignInNonce,
  loadGoogleIdentity,
  type GoogleCredentialResponse,
} from "@/lib/google-identity";
import { safeRedirect } from "@/lib/safe-redirect";
import { createClient } from "@/lib/supabase/client";

/** GIS clamps rendered buttons to this range (pixels). */
const MIN_BUTTON_WIDTH = 200;
const MAX_BUTTON_WIDTH = 400;

/** How long to wait for Google to actually paint its button. */
const RENDER_TIMEOUT_MS = 2500;

/**
 * Resolve once Google has painted something into `container`.
 *
 * `renderButton()` reports nothing when it declines to draw — an origin that
 * is not in the client's Authorized JavaScript origins, a client ID that does
 * not exist, or a browser that blocks the embed all fail this way, leaving an
 * empty div and a console message from Google. Watching the box is the only
 * reliable signal, and without it the user stares at a spinner forever.
 */
function waitForRenderedButton(
  container: HTMLElement,
  timeoutMs = RENDER_TIMEOUT_MS,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;

    const poll = () => {
      if (container.childElementCount > 0 && container.getBoundingClientRect().height > 0) {
        resolve();
        return;
      }

      if (Date.now() > deadline) {
        reject(
          new Error(
            "Google did not render its button. The page origin is probably " +
              "missing from the OAuth client's Authorized JavaScript origins, " +
              "or NEXT_PUBLIC_GOOGLE_CLIENT_ID points at a client that does " +
              "not exist. Google logs the specific reason to the console.",
          ),
        );
        return;
      }

      requestAnimationFrame(poll);
    };

    requestAnimationFrame(poll);
  });
}

type Phase = "loading" | "ready" | "signing-in" | "unavailable";

/**
 * "Continue with Google" rendered by Google Identity Services.
 *
 * Google draws its own button into `containerRef` and, on success, hands back
 * an ID token for the chosen account. That token is exchanged for a Supabase
 * session with `signInWithIdToken()` — no navigation to
 * `<project-ref>.supabase.co` at any point, which is the whole reason this
 * component exists: Google's prompt names the Authorized JavaScript origin
 * (our domain) instead of the Supabase project host.
 *
 * Requires, in Google Cloud -> Auth Platform -> Clients -> (Web client):
 *   - Authorized JavaScript origins: every origin this app is served from.
 * ...and in Supabase -> Authentication -> Sign In / Providers -> Google:
 *   - the same client ID present in "Client IDs" (Supabase validates the
 *     token's `aud` claim against that list).
 *
 * If GIS cannot load (offline, content blocker, unsupported browser) this
 * falls back to `GoogleRedirectButton` so sign-in still works — only the
 * consent-screen wording regresses.
 */
export default function GoogleIdentityButton({
  label,
  intent = "signin",
  redirectTo = "/dashboard",
}: {
  label?: string;
  intent?: "signin" | "signup";
  redirectTo?: string;
}) {
  const router = useRouter();

  const containerRef = useRef<HTMLDivElement | null>(null);
  /** Raw nonce for the token currently being minted by Google. */
  const nonceRef = useRef<string | null>(null);
  /** Guards against state updates after unmount (GIS callbacks are async). */
  const mountedRef = useRef(true);

  const { configured } = getSupabaseEnvStatus();
  const { enabled, clientId } = getGoogleIdentityStatus();

  /*
   * Both flags come from NEXT_PUBLIC_* values inlined at build time, so they
   * are known during the first render — deciding the initial phase here
   * avoids a setState-in-effect cascade.
   */
  const usable = configured && enabled;

  const [phase, setPhase] = useState<Phase>(usable ? "loading" : "unavailable");
  const [error, setError] = useState<string | null>(null);

  /** Exchange Google's ID token for a Supabase session. */
  const handleCredential = useCallback(
    async (response: GoogleCredentialResponse) => {
      if (!mountedRef.current) return;

      setError(null);
      setPhase("signing-in");

      try {
        const supabase = createClient();

        const nonce = nonceRef.current;

        const { error: signInError } = await supabase.auth.signInWithIdToken({
          provider: "google",
          token: response.credential,
          // Omit entirely when no nonce was sent to Google: Supabase rejects
          // a mismatch in either direction.
          ...(nonce ? { nonce } : {}),
        });

        if (signInError) {
          console.error("Google ID-token sign-in error:", signInError);

          if (!mountedRef.current) return;

          setError(describeIdTokenError(signInError.message) ?? signInError.message);
          setPhase("ready");
          return;
        }
      } catch (err) {
        console.error("Google ID-token sign-in failed:", err);

        if (!mountedRef.current) return;

        setError(describeAuthError(err));
        setPhase("ready");
        return;
      }

      // The session cookie is set by createBrowserClient; refresh() makes the
      // server components (and the proxy's session check) see it.
      router.replace(safeRedirect(redirectTo));
      router.refresh();
    },
    [redirectTo, router],
  );

  useEffect(() => {
    mountedRef.current = true;

    if (!usable) return;

    let cancelled = false;

    (async () => {
      try {
        const [accounts, nonce] = await Promise.all([
          loadGoogleIdentity(),
          createSignInNonce(),
        ]);

        const container = containerRef.current;

        if (cancelled || !container) return;

        nonceRef.current = nonce?.raw ?? null;

        accounts.initialize({
          client_id: clientId,
          callback: (response) => void handleCredential(response),
          ...(nonce ? { nonce: nonce.hashed } : {}),
          // Never sign somebody in without them asking: this button also sits
          // on the signup page.
          auto_select: false,
          context: intent === "signup" ? "signup" : "signin",
          ux_mode: "popup",
          itp_support: true,
          use_fedcm_for_prompt: true,
        });

        // Strict Mode runs effects twice in development; without this the
        // second pass appends a second Google button.
        container.replaceChildren();

        const measured = Math.round(container.getBoundingClientRect().width);

        accounts.renderButton(container, {
          type: "standard",
          theme: "outline",
          size: "large",
          text: intent === "signup" ? "signup_with" : "continue_with",
          shape: "pill",
          logo_alignment: "center",
          width: Math.min(
            MAX_BUTTON_WIDTH,
            Math.max(MIN_BUTTON_WIDTH, measured || MIN_BUTTON_WIDTH),
          ),
        });

        // renderButton() is fire-and-forget: confirm it actually drew.
        await waitForRenderedButton(container);

        if (!cancelled) setPhase("ready");
      } catch (err) {
        // Offline, blocked script, unsupported browser: the redirect flow is
        // a working (if less pretty) substitute, so say nothing to the user.
        console.warn(
          "Google Identity Services unavailable, falling back to the Supabase " +
            "redirect flow:",
          err,
        );

        if (!cancelled) setPhase("unavailable");
      }
    })();

    return () => {
      cancelled = true;
      mountedRef.current = false;

      // Dismiss any open One Tap / FedCM UI belonging to this mount.
      window.google?.accounts?.id?.cancel();
    };
  }, [clientId, handleCredential, intent, usable]);

  if (phase === "unavailable") {
    return <GoogleRedirectButton label={label} />;
  }

  return (
    <div className="w-full">
      <div className="relative flex w-full justify-center">
        {/* Google draws its button in here. */}
        <div
          ref={containerRef}
          className={`flex w-full justify-center ${
            phase === "ready" ? "" : "pointer-events-none opacity-0"
          }`}
        />

        {phase !== "ready" && (
          <div
            className="absolute inset-0 flex items-center justify-center gap-2 rounded-full border border-zinc-200 text-sm text-zinc-500 dark:border-zinc-800 dark:text-zinc-400"
            role="status"
            aria-live="polite"
          >
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            {phase === "signing-in" ? "Signing you in…" : "Loading Google…"}
          </div>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="mt-2 flex items-start gap-1.5 text-left text-xs leading-relaxed text-rose-600 dark:text-rose-400"
        >
          <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}
