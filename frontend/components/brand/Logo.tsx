import { Sparkles } from "lucide-react";

/**
 * AgentFlow AI logo mark + wordmark.
 *
 * The mark is a gradient rounded square with a sparkle glyph.
 * `dark` renders a light-on-dark wordmark (for dark brand panels).
 */
export default function Logo({
  dark = false,
  size = "md",
}: {
  dark?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  const markSize =
    size === "lg" ? "h-11 w-11 rounded-2xl" : size === "md" ? "h-9 w-9 rounded-xl" : "h-8 w-8 rounded-lg";
  const iconSize = size === "lg" ? 22 : size === "md" ? 18 : 16;
  const wordmark = size === "lg" ? "text-xl" : size === "md" ? "text-lg" : "text-base";

  return (
    <span className="inline-flex items-center gap-2.5">
      <span
        className={`inline-flex items-center justify-center bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-white shadow-lg shadow-indigo-500/30 ${markSize}`}
      >
        <Sparkles size={iconSize} aria-hidden="true" />
      </span>
      <span
        className={`font-semibold tracking-tight ${wordmark} ${
          dark ? "text-white" : "text-zinc-900 dark:text-white"
        }`}
      >
        AgentFlow<span className={dark ? "text-indigo-300" : "text-indigo-500"}> AI</span>
      </span>
    </span>
  );
}
