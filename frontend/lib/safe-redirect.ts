/**
 * Safe post-auth redirect target.
 *
 * A redirect value may only point at an *internal* path. This blocks
 * protocol-relative (``//evil.com``) and backslash (``/\\evil.com``) open
 * redirects while still allowing any local path such as ``/dashboard`` or
 * ``/organizations/<id>``.
 */

export function isSafeInternalPath(value: string | null | undefined): boolean {
  return (
    typeof value === "string" &&
    value.startsWith("/") &&
    !value.startsWith("//") &&
    !value.startsWith("/\\")
  );
}

export function safeRedirect(
  value: string | null | undefined,
  fallback = "/dashboard",
): string {
  return isSafeInternalPath(value) ? (value as string) : fallback;
}
