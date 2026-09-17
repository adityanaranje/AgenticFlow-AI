"use client";

import { useCallback, useEffect, useState } from "react";
import { Gauge, Loader2, RefreshCw } from "lucide-react";

import { apiClient } from "@/lib/api/client";

/**
 * Live view of the signed-in user's LLM token budget.
 *
 * Polls `GET /organizations/{org}/research/quota` (the backend counts real
 * model usage in fixed hourly/daily windows per user) and shows how much is
 * left. Never blocks the page: on fetch failure it collapses to a one-line
 * note. `remaining` is null for a disabled limit (0 = unlimited).
 */

interface QuotaWindow {
  used: number;
  limit: number;
  remaining: number | null;
}

interface QuotaStatus {
  user_id: string;
  enforced: boolean;
  run_token_budget: number;
  hourly: QuotaWindow;
  daily: QuotaWindow;
  concurrent_runs: { active: number; limit: number };
}

const POLL_MS = 30_000;
const nf = new Intl.NumberFormat("en");

function barTone(fraction: number): string {
  if (fraction >= 1) return "bg-rose-500";
  if (fraction > 0.8) return "bg-amber-500";
  return "bg-indigo-500";
}

function QuotaRow({ label, window }: { label: string; window: QuotaWindow }) {
  const unlimited = window.limit <= 0;
  const fraction = unlimited ? 0 : Math.min(1, window.used / window.limit);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium text-zinc-700 dark:text-zinc-200">{label}</span>
        <span className="tabular-nums text-zinc-500 dark:text-zinc-400">
          {unlimited ? (
            "unlimited"
          ) : (
            <>
              <span className="font-semibold text-zinc-900 dark:text-white">
                {nf.format(Math.max(0, window.remaining ?? 0))}
              </span>{" "}
              of {nf.format(window.limit)} left
            </>
          )}
        </span>
      </div>
      <div
        className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800"
        role="progressbar"
        aria-label={`${label} token usage`}
        aria-valuenow={Math.round(fraction * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`h-full rounded-full transition-all ${barTone(fraction)}`}
          style={{ width: `${Math.max(2, Math.round(fraction * 100))}%` }}
        />
      </div>
    </div>
  );
}

export default function TokenQuotaCard({ organizationId }: { organizationId: string }) {
  const [status, setStatus] = useState<QuotaStatus | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await apiClient.get<QuotaStatus>(
        `/organizations/${organizationId}/research/quota`,
      );
      setStatus(data);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    // Initial load: the state updates inside load() only happen after the
    // network round-trip (post-await), never during the commit phase that
    // the rule guards against — hence the targeted disable.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  if (error && !status) {
    return (
      <p className="text-xs text-zinc-400">
        Token usage details are unavailable right now.
      </p>
    );
  }

  const runsUnlimited = (status?.concurrent_runs.limit ?? 0) <= 0;

  return (
    <section className="card p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-900 dark:text-white">
          <Gauge className="h-4 w-4 text-indigo-500" aria-hidden="true" />
          Your token budget
        </h2>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          aria-label="Refresh token usage"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {status ? (
        <div className="mt-4 space-y-4">
          <QuotaRow label="Today" window={status.daily} />
          <QuotaRow label="This hour" window={status.hourly} />
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
            <span>
              Research runs in flight:{" "}
              <strong className="text-zinc-700 dark:text-zinc-200">
                {status.concurrent_runs.active}
              </strong>{" "}
              {runsUnlimited ? "" : `of ${status.concurrent_runs.limit}`}
            </span>
            {!status.enforced && (
              <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                <Loader2 className="h-3 w-3" aria-hidden="true" />
                Usage tracking is offline (Redis down) — limits not enforced
              </span>
            )}
          </div>
        </div>
      ) : (
        <p className="mt-4 flex items-center gap-2 text-sm text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading token usage…
        </p>
      )}
    </section>
  );
}
