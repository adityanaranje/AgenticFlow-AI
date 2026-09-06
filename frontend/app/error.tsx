"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("AgentFlow AI UI error:", error);
  }, [error]);

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: "24px",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "420px",
          textAlign: "center",
        }}
      >
        <h1>Something went wrong</h1>
        <p style={{ marginTop: "8px", color: "#71717a" }}>
          An unexpected error occurred while rendering this page.
        </p>
        {error.digest && (
          <p
            style={{
              marginTop: "12px",
              fontSize: "12px",
              color: "#a1a1aa",
              wordBreak: "break-all",
            }}
          >
            Digest: {error.digest}
          </p>
        )}
        <button
          type="button"
          onClick={() => reset()}
          style={{
            marginTop: "24px",
            padding: "10px 20px",
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </div>
    </main>
  );
}
