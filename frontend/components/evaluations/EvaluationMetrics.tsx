"use client";

import { CheckCircle2, AlertCircle, TrendingUp } from "lucide-react";

type Metrics = {
  citation_correctness?: number | null;
  citation_completeness?: number | null;
  groundedness?: number | null;
  relevance?: number | null;
  answer_quality?: number | null;
};

const METRIC_INFO: Record<
  keyof Metrics,
  { label: string; description: string; icon: "success" | "warning" | "info" }
> = {
  citation_correctness: {
    label: "Citation Correctness",
    description: "Fraction of in-text citations that map to a grounded source.",
    icon: "success",
  },
  citation_completeness: {
    label: "Citation Completeness",
    description: "Fraction of grounded sources actually cited in the report.",
    icon: "info",
  },
  groundedness: {
    label: "Groundedness",
    description: "Fraction of report sentences that carry a citation.",
    icon: "info",
  },
  relevance: {
    label: "Relevance",
    description: "Mean retrieval score of the cited sources.",
    icon: "warning",
  },
  answer_quality: {
    label: "Answer Quality",
    description: "LLM-judged or objective-mean quality score.",
    icon: "success",
  },
};

function scoreColor(score: number): string {
  if (score >= 0.8) return "bg-emerald-500";
  if (score >= 0.5) return "bg-amber-500";
  return "bg-rose-500";
}

function scoreTextColor(score: number): string {
  if (score >= 0.8) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 0.5) return "text-amber-600 dark:text-amber-400";
  return "text-rose-600 dark:text-rose-400";
}

function scoreBgColor(score: number): string {
  if (score >= 0.8) return "bg-emerald-100 dark:bg-emerald-500/15";
  if (score >= 0.5) return "bg-amber-100 dark:bg-amber-500/15";
  return "bg-rose-100 dark:bg-rose-500/15";
}

export default function EvaluationMetrics({
  metrics,
  compact = false,
}: {
  metrics: Metrics;
  compact?: boolean;
}) {
  const entries = Object.entries(METRIC_INFO)
    .filter(([key]) => metrics[key as keyof Metrics] != null)
    .map(([key, info]) => ({
      key: key as keyof Metrics,
      ...info,
      score: metrics[key as keyof Metrics] as number,
    }));

  if (entries.length === 0) {
    return (
      <p className="text-sm text-zinc-400">No metrics available.</p>
    );
  }

  // Overall score = mean of all available metrics
  const overall =
    entries.reduce((sum, e) => sum + e.score, 0) / entries.length;

  return (
    <div className={compact ? "space-y-3" : "space-y-5"}>
      {/* Overall badge */}
      <div className="flex items-center gap-3">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-bold ${scoreBgColor(overall)} ${scoreTextColor(overall)}`}
        >
          <TrendingUp className="h-4 w-4" aria-hidden="true" />
          {Math.round(overall * 100)}% overall
        </span>
      </div>

      {/* Individual metrics */}
      {entries.map(({ key, label, description, score }) => (
        <div key={key} className="group">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              {score >= 0.8 ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" aria-hidden="true" />
              ) : score >= 0.5 ? (
                <AlertCircle className="h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />
              ) : (
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-500" aria-hidden="true" />
              )}
              <span className="text-sm font-medium text-zinc-900 dark:text-white truncate">
                {label}
              </span>
            </div>
            <span className={`text-sm font-bold tabular-nums ${scoreTextColor(score)}`}>
              {Math.round(score * 100)}%
            </span>
          </div>

          {!compact && (
            <p className="mt-0.5 ml-6 text-xs text-zinc-400">{description}</p>
          )}

          {/* Progress bar */}
          <div className={`mt-1.5 ${compact ? "" : "ml-6"} h-2 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800`}>
            <div
              className={`h-full rounded-full transition-all duration-500 ${scoreColor(score)}`}
              style={{ width: `${Math.round(score * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
