"""Lightweight Langfuse tracing helpers for the ingestion and research pipelines.

Every helper degrades to a no-op when Langfuse is not configured (or the
installed SDK differs), so tracing never blocks ingestion or research.

A **trace** is the top-level unit in Langfuse (one per research run or
document ingestion).  Child **spans** and **generations** (LLM calls)
are attached to that trace so the Langfuse UI shows a proper tree.

Privacy: callers pass only non-sensitive ``metadata`` (ids, counts, sizes).
Raw file contents and secrets are never forwarded to these helpers.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any, Optional

from app.core.langfuse import get_langfuse
from app.core.logging import get_logger

logger = get_logger(__name__)


class _NoopSpan:
    """Context-manager no-op used when Langfuse is unavailable."""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def end(self) -> None:
        return None

    def update(self, **_kwargs) -> None:
        return None


# ---------------------------------------------------------------------------
# Trace management
# ---------------------------------------------------------------------------

def start_trace(
    name: str,
    *,
    metadata: Optional[dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Any | None:
    """Create and return a new Langfuse trace (or ``None`` if unavailable).

    A trace is the root of every span/generation tree.  One trace per
    research run or document ingestion keeps the Langfuse UI tidy.
    """
    client = get_langfuse()
    if client is None:
        return None

    try:
        return client.trace(
            name=name,
            metadata=metadata or {},
            user_id=user_id,
        )
    except Exception:
        logger.debug("Langfuse trace creation failed; tracing disabled for %s", name)
        return None


def flush_langfuse_events() -> None:
    """Flush pending Langfuse events (called on shutdown)."""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        logger.exception("Failed to flush Langfuse events.")


# ---------------------------------------------------------------------------
# Spans
# ---------------------------------------------------------------------------

def ingestion_span(
    name: str,
    *,
    metadata: Optional[dict[str, Any]] = None,
    input_data: Any = None,
    trace: Any | None = None,
) -> Any:
    """Return a context-managed Langfuse span for ``name`` (no-op if absent).

    When *trace* is provided the span is attached to that trace; otherwise
    it falls back to creating a standalone span on the client (Langfuse ≥2.5
    accepts this, though the UI will show it at the top level).
    """
    client = get_langfuse()
    if client is None:
        return _NoopSpan()

    kwargs: dict[str, Any] = {
        "name": name,
        "metadata": metadata or {},
    }
    if input_data is not None:
        kwargs["input"] = input_data

    # Prefer attaching to the provided trace object.
    target = trace if trace is not None else client

    # langfuse v2: .span() / .start_span(); v3: .start_span().
    for method_name in ("start_span", "span"):
        method = getattr(target, method_name, None)
        if not callable(method):
            continue
        try:
            span = method(**kwargs)
            # Always wrap in _SpanWrapper so __exit__ calls end(), ensuring
            # Langfuse marks the span as finished even when the SDK's own
            # context manager doesn't.
            return _SpanWrapper(span)
        except Exception:
            logger.debug("Langfuse %s failed; tracing disabled.", method_name)
            break

    return _NoopSpan()


class _SpanWrapper:
    """Thin wrapper that adds the context-manager protocol around a Langfuse
    span object when the SDK returns one without ``__enter__``/``__exit__``."""

    def __init__(self, span: Any):
        self._span = span

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        try:
            self._span.end()
        except Exception:
            pass
        return False

    def end(self) -> None:
        try:
            self._span.end()
        except Exception:
            pass

    def update(self, **kwargs: Any) -> None:
        try:
            self._span.update(**kwargs)
        except Exception:
            pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._span, name)


# ---------------------------------------------------------------------------
# Generations (LLM calls)
# ---------------------------------------------------------------------------

def llm_generation(
    name: str,
    *,
    model: str = "",
    input_data: Any = None,
    output: Any = None,
    metadata: Optional[dict[str, Any]] = None,
    trace: Any | None = None,
    usage: Optional[dict[str, int]] = None,
    start_time: Optional[float] = None,
) -> Any:
    """Record an LLM generation (model call) in Langfuse.

    Returns the generation object so the caller can ``.end()`` it after the
    response arrives.  Falls back to a no-op when Langfuse is absent.
    """
    client = get_langfuse()
    if client is None:
        return _NoopSpan()

    target = trace if trace is not None else client
    kwargs: dict[str, Any] = {
        "name": name,
        "model": model,
        "metadata": metadata or {},
    }
    if input_data is not None:
        kwargs["input"] = input_data
    if output is not None:
        kwargs["output"] = output
    if usage:
        kwargs["usage"] = usage
    if start_time:
        kwargs["start_time"] = start_time

    for method_name in ("start_generation", "generation"):
        method = getattr(target, method_name, None)
        if not callable(method):
            continue
        try:
            gen = method(**kwargs)
            return _SpanWrapper(gen)
        except Exception:
            logger.debug("Langfuse %s failed.", method_name)
            break

    return _NoopSpan()


# ---------------------------------------------------------------------------
# Gauge / observation
# ---------------------------------------------------------------------------

def record_gauge(name: str, value: Any, metadata: Optional[dict[str, Any]] = None) -> None:
    """Log an observation against the Langfuse client when present."""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.span(name=name, metadata={"value": value, **(metadata or {})})
    except Exception:
        logger.debug("Langfuse gauge %s failed; ignored.", name)
