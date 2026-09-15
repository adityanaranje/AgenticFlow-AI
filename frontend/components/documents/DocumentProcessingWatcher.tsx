"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Keeps a document detail page in sync while ingestion is running.
 *
 * Ingestion happens in the worker / background pool: page content, chunk
 * count and status are only known once it finishes. While the document is
 * `pending` or `processing` this component asks Next.js to re-render the
 * server component periodically, then stops on a terminal status (or
 * unmount). Nothing is rendered.
 */
export default function DocumentProcessingWatcher({
  status,
  intervalMs = 3000,
}: {
  status: string | null | undefined;
  intervalMs?: number;
}) {
  const router = useRouter();
  const active = status === "pending" || status === "processing";

  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => router.refresh(), intervalMs);
    return () => clearInterval(timer);
  }, [active, intervalMs, router]);

  return null;
}
