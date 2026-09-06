export default function Loading() {
  return (
    <div
      className="flex flex-1 items-center justify-center"
      style={{ minHeight: "60vh" }}
      role="status"
      aria-label="Loading"
    >
      <div className="flex flex-col items-center gap-4">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900 dark:border-zinc-700 dark:border-t-zinc-100" />
        <span className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</span>
      </div>
    </div>
  );
}
