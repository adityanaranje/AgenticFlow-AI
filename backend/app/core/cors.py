"""CORS allowlist construction.

The Next.js frontend calls this API from the browser, so every non-simple
request (a ``multipart/form-data`` document upload, an ``Authorization``
header, a ``PUT``) is preceded by an ``OPTIONS`` preflight. Starlette's
``CORSMiddleware`` rejects a preflight whose ``Origin`` is not in the
allowlist with

    HTTP/1.1 400 Bad Request
    Disallowed CORS origin

...which is the exact line this module exists to prevent. Two things produced
it in practice:

1. ``allow_origins`` was built from the single ``FRONTEND_URL`` string, so
   ``http://127.0.0.1:3000`` (the same dev server, opened by IP) or a preview
   deployment origin was never allowed. Only one origin worked.
2. A trailing slash, missing scheme or a typo in ``FRONTEND_URL`` silently
   produced an allowlist entry that can never match an ``Origin`` header,
   because browsers send the origin as ``scheme://host[:port]`` with no path
   and no trailing slash.

So the allowlist is built here, from a comma-separated list, with each entry
validated *and normalised* the way a browser sends it. In development the
loopback aliases of a configured dev origin (``localhost`` / ``127.0.0.1`` /
``[::1]``, any port) match as well, because Next.js silently moves to ``3001``
when ``3000`` is taken and opening the app by IP is the same dev server.
Production matches only what is configured.

Configuration (see ``app.core.config``):

``FRONTEND_URL``
    One or more allowed browser origins, comma-separated, e.g.
    ``https://app.example.com`` or
    ``http://localhost:3000,http://127.0.0.1:3000``.
    A ``*`` segment is supported inside the host for preview deployments,
    e.g. ``https://*.vercel.app``.

``FRONTEND_ORIGIN_REGEX``
    Optional escape hatch for deployments whose origins cannot be listed
    (many rotating preview domains). Anchored automatically; it is *added to*
    the explicit list, never replaces it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.logging import get_logger

logger = get_logger(__name__)

#: Sensible default when nothing is configured: the local Next.js dev server.
DEFAULT_ORIGIN = "http://localhost:3000"

#: Hosts that all address the same machine. A browser sends whichever one the
#: user typed, so in development they are interchangeable. IPv6 literals are
#: bracketed, exactly as they appear in an Origin header.
LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "[::1]")

_ALLOWED_SCHEMES = frozenset({"http", "https"})

#: In development the dev server is reached by several spellings *and* often on
#: a different port than configured (Next.js silently moves to 3001 when 3000
#: is taken, Vite may pick 5173). All of those are the same machine, so a
#: loopback origin is matched by pattern too — never in production.
LOOPBACK_ANY_PORT_REGEX = r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?"


class CorsConfigError(ValueError):
    """``FRONTEND_URL`` / ``FRONTEND_ORIGIN_REGEX`` cannot be parsed."""


@dataclass(frozen=True)
class CorsConfig:
    """Ready-to-use arguments for ``CORSMiddleware``."""

    allow_origins: list[str]
    allow_origin_regex: str | None
    #: Answer Chrome's Private Network Access preflight. Only meaningful when
    #: a page on a public origin (an HTTPS preview / tunnel) calls a backend
    #: on localhost or a LAN address.
    allow_private_network: bool = False


def _split_entries(raw: str) -> list[str]:
    """Split a comma/whitespace/newline separated value, dropping blanks.

    Env values are easy to paste with newlines or with surrounding quotes
    (``FRONTEND_URL="https://app.example.com"``), so those are tolerated.
    """
    entries: list[str] = []
    for chunk in re.split(r"[,\s]+", raw or ""):
        entry = chunk.strip().strip("\"'").strip()
        if entry:
            entries.append(entry)
    return entries


def normalize_origin(value: str) -> str:
    """Return *value* as a browser ``Origin`` header would look.

    ``http://localhost:3000/`` and ``HTTP://LocalHost:3000`` both become
    ``http://localhost:3000``. Raises :class:`CorsConfigError` when the value
    could never match an ``Origin`` header (path, missing scheme, ...), so a
    typo fails loudly at startup instead of as a mystery 400 in the browser.
    """
    candidate = value.strip().strip("\"'").strip().rstrip("/")
    if not candidate:
        raise CorsConfigError("empty origin")

    if "://" not in candidate:
        raise CorsConfigError(
            f"{value!r} has no scheme — use scheme://host[:port], "
            f"e.g. 'https://app.example.com' or '{DEFAULT_ORIGIN}'"
        )

    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise CorsConfigError(
            f"{value!r} uses scheme {scheme!r} — only http and https can "
            f"appear in an Origin header"
        )
    if not parts.hostname:
        raise CorsConfigError(f"{value!r} has no host")
    if parts.path or parts.query or parts.fragment:
        raise CorsConfigError(
            f"{value!r} must be an origin only (scheme + host + optional "
            f"port), with no path, query or fragment"
        )

    try:
        port = parts.port
    except ValueError as exc:  # invalid port (e.g. "http://host:abc")
        raise CorsConfigError(f"{value!r} has an invalid port") from exc

    host = parts.hostname
    if ":" in host:  # IPv6 literal -> [::1]
        host = f"[{host}]"

    return f"{scheme}://{host}{f':{port}' if port else ''}"


def _loopback_aliases(origin: str) -> list[str]:
    """Other spellings of the same loopback dev server (``localhost`` etc.)."""
    parts = urlsplit(origin)
    hostname = parts.hostname or ""
    if hostname not in LOOPBACK_HOSTS:
        return []

    current = f"[{hostname}]" if ":" in hostname else hostname
    scheme = parts.scheme
    port = f":{parts.port}" if parts.port else ""
    return [
        f"{scheme}://{candidate}{port}"
        for candidate in LOOPBACK_HOSTS
        if candidate != current
    ]


def _wildcard_to_regex(entry: str) -> str | None:
    """Translate ``https://*.example.com`` into an anchored regex body.

    Returns ``None`` when *entry* contains no wildcard. Only a whole host
    segment may be a wildcard: ``*.example.com`` and ``app-*.example.com``
    work, ``*`` alone is rejected by the caller.
    """
    if "*" not in entry:
        return None

    normalized = normalize_origin(entry.replace("*", "wildcard"))
    if "wildcard" not in normalized:
        raise CorsConfigError(f"{entry!r} contains a wildcard outside the host")

    host = normalized.split("://", 1)[1]
    if host == "wildcard":
        # A bare "*" host would allow every origin of that scheme, which is
        # exactly what credentialed requests must never do.
        raise CorsConfigError(
            f"{entry!r} wildcards the whole host — name at least one host "
            f"label, e.g. 'https://*.vercel.app'"
        )

    pieces = [re.escape(piece) for piece in normalized.split("wildcard")]
    # A wildcard expands to one or more host-label characters, never to a
    # "/" or a dot, so "*" cannot escape the host it was written for.
    return "[A-Za-z0-9.-]+".join(pieces)


def build_cors_config(
    frontend_url: str = "",
    origin_regex: str = "",
    environment: str = "development",
    allow_private_network: bool | None = None,
) -> CorsConfig:
    """Build the ``CORSMiddleware`` allowlist from configuration.

    Failure mode is deliberate: this never raises. An unusable entry (a bare
    ``*``, a path, a missing scheme) is logged with the reason and skipped, so
    the API still boots and the misconfiguration is visible in the log instead
    of the process dying on a typo — or of a ``*`` silently allowing every
    origin on a credentialed API.

    The resolved allowlist is logged by ``app.main`` during startup (logging is
    not configured yet while this module is imported).
    """
    # Note: a bare "*" is never honoured — credentialed CORS forbids it. It is
    # logged and dropped like any other unusable entry (fail closed), so a
    # misconfiguration can never silently allow every origin.
    raw = (frontend_url or "").strip()
    entries = _split_entries(raw) or [DEFAULT_ORIGIN]

    allow_origins: list[str] = []
    patterns: list[str] = []

    def add_origin(origin: str) -> None:
        if origin not in allow_origins:
            allow_origins.append(origin)

    explicit_entries: list[str] = []
    for entry in entries:
        if "*" in entry:
            explicit_entries.append(entry)
            continue
        try:
            add_origin(normalize_origin(entry))
        except CorsConfigError as exc:
            logger.error(
                "Ignoring invalid FRONTEND_URL entry %r: %s. "
                "The browser origin must match exactly, so this would cause "
                "a CORS preflight 400 (Disallowed CORS origin).",
                entry,
                exc,
            )

    for entry in explicit_entries:
        try:
            pattern = _wildcard_to_regex(entry)
        except CorsConfigError as exc:
            logger.error("Ignoring invalid FRONTEND_URL entry %r: %s.", entry, exc)
            continue
        if pattern is not None and pattern not in patterns:
            patterns.append(pattern)

    # Dev convenience: localhost, 127.0.0.1 and [::1] are the same server, and
    # the dev server may well be on another port than the configured one.
    if environment != "production":
        # Snapshot first: add_origin() appends while aliases are collected.
        aliases = [alias for origin in allow_origins for alias in _loopback_aliases(origin)]
        for alias in aliases:
            add_origin(alias)

        loopback_configured = any(
            urlsplit(origin).hostname in LOOPBACK_HOSTS for origin in allow_origins
        )
        if loopback_configured and LOOPBACK_ANY_PORT_REGEX not in patterns:
            patterns.append(LOOPBACK_ANY_PORT_REGEX)

    user_regex = (origin_regex or "").strip()
    if user_regex:
        # Accept both "example.com" style fragments and fully anchored
        # expressions; the surrounding ^(?: ... )$ is applied once below.
        body = user_regex.removeprefix("^").removesuffix("$")
        try:
            re.compile(f"(?:{body})")
        except re.error as exc:
            logger.error(
                "Ignoring invalid FRONTEND_ORIGIN_REGEX %r: %s.", user_regex, exc
            )
        else:
            if body not in patterns:
                patterns.append(body)

    allow_origin_regex = f"^(?:{'|'.join(patterns)})$" if patterns else None

    if allow_private_network is None:
        # Chrome only sends this preflight when a non-secure-context page
        # reaches a private address, i.e. local dev / previews — never in a
        # deployed production pair. Default it on there, off in production.
        allow_private_network = environment != "production"

    return CorsConfig(
        allow_origins=allow_origins,
        allow_origin_regex=allow_origin_regex,
        allow_private_network=allow_private_network,
    )


def describe_cors_config(config: CorsConfig) -> str:
    """One-line, log-friendly summary of an effective allowlist."""
    return (
        f"origins={config.allow_origins} "
        f"regex={config.allow_origin_regex} "
        f"private_network={config.allow_private_network}"
    )


def cors_allowed_origins(
    frontend_url: str = "",
    origin_regex: str = "",
    environment: str = "development",
) -> list[str]:
    """Backwards-friendly helper returning only the explicit origins."""
    return build_cors_config(frontend_url, origin_regex, environment).allow_origins
