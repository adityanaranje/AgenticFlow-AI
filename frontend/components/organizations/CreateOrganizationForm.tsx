"use client";

import { useState, type SubmitEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Building2, CircleAlert, Loader2 } from "lucide-react";

/**
 * Client form for creating an organization.
 *
 * Submits to POST /api/organizations, which authenticates the caller's
 * Supabase session, validates the name, and calls the secured
 * `create_organization` DB function (owner membership is created server-side
 * under `auth.uid()` — never inserted from the browser).
 */
export default function CreateOrganizationForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmed = name.trim();

    if (!trimmed) {
      setError("Please enter an organization name.");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const response = await fetch("/api/organizations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });

      const payload = (await response.json().catch(() => null)) as {
        organization?: { id?: string };
        error?: string;
      } | null;

      if (!response.ok) {
        setError(payload?.error ?? "Could not create the organization.");
        setLoading(false);
        return;
      }

      const organizationId = payload?.organization?.id;

      if (!organizationId) {
        setError("The organization was created but returned no id.");
        setLoading(false);
        return;
      }

      router.push(`/organizations/${organizationId}`);
      router.refresh();
    } catch (err) {
      console.error("Failed to create organization:", err);
      setError("A network error occurred. Please try again.");
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label htmlFor="org-name" className="label">
          Organization name
        </label>
        <div className="relative">
          <Building2
            className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
            aria-hidden="true"
          />
          <input
            id="org-name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={120}
            autoComplete="organization"
            placeholder="Acme Research Labs"
            className="input-field pl-10"
          />
        </div>
        <p className="mt-1.5 text-xs text-zinc-400 dark:text-zinc-500">
          Your team will share documents and research inside this space.
        </p>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        className="btn-primary btn-block"
      >
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Creating organization…
          </>
        ) : (
          <>
            Create organization
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </>
        )}
      </button>
    </form>
  );
}
