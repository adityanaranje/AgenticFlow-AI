"""Shared retry policy for remote provider calls.

Document ingestion (:mod:`app.services.embeddings`) and the research agents
(:mod:`app.agents.llm`) both call providers whose failures are frequently
transient — rate limits, socket timeouts, 5xx responses. Both also need the
*same* rule about what must never be retried (a malformed request, an auth
failure or an exhausted quota will fail identically on every attempt), so the
classification and the backoff live here instead of being duplicated.

Callers that need deterministic tests inject their own ``sleep``.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

# ``TypeVar`` rather than PEP 695 syntax: the runtime floor is Python 3.11
# (see README prerequisites), where ``def f[T](...)`` is a syntax error.
T = TypeVar("T")

# HTTP statuses that may succeed on a later attempt.
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

# Exception class names that mean "try again later". Matching on the name
# keeps this working across SDK versions whose module layout differs (the
# OpenAI SDK moved its error classes between releases) without importing a
# private error hierarchy.
RETRYABLE_ERROR_NAMES = frozenset(
    {
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
        "APIStatusError",
        "ConnectTimeout",
        "ReadTimeout",
        "Timeout",
        "TimeoutError",
        "ConnectionError",
        "ConnectionResetError",
        "ServiceUnavailableError",
    }
)

# Indirection so tests (and future async runtimes) can replace the sleeper
# without patching the global ``time`` module.
_sleep = time.sleep


def is_retryable_error(exc: BaseException) -> bool:
    """Whether ``exc`` looks like a transient provider error."""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    if isinstance(status, int) and status in RETRYABLE_STATUS_CODES:
        return True
    return type(exc).__name__ in RETRYABLE_ERROR_NAMES


def retry_delay(
    attempt: int, *, base: float = 0.5, cap: float = 8.0
) -> float:
    """Exponential backoff with jitter for ``attempt`` (1-based) seconds."""
    window = min(cap, base * (2 ** max(0, attempt - 1)))
    return window * (0.5 + random.random())


def call_with_retries(  # noqa: UP047 - PEP 695 generics need Python 3.12+
    func: Callable[[], T],
    *,
    attempts: int = 3,
    sleep: Callable[[float], Any] | None = None,
    on_retry: Callable[[int, BaseException, float], Any] | None = None,
) -> T:
    """Call ``func()``, retrying transient failures with backoff.

    Non-retryable errors (and the final attempt of a retryable one) propagate
    unchanged so callers see the provider's real error.
    """
    sleeper = sleep or _sleep
    total = max(1, int(attempts))
    last_error: BaseException | None = None

    for attempt in range(1, total + 1):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            if attempt >= total or not is_retryable_error(exc):
                raise
            delay = retry_delay(attempt)
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            sleeper(delay)

    raise last_error  # pragma: no cover - the loop always returns or raises
