"""Lightweight Langfuse tracing helpers for the ingestion and research pipelines.

Every helper degrades to a no-op when Langfuse is not configured (or the
installed SDK differs), so tracing never blocks ingestion or research.

Langfuse v4 (the installed version) uses an observation-based API:

    - ``client.start_observation()`` creates a root span (the "trace").
    - ``parent.start_observation()`` creates a child span.
    - ``as_type`` controls the observation kind (span, generation, etc).
    - ``TraceContext`` links observations to an existing trace.

Privacy: callers pass only non-sensitive ``metadata`` (ids, counts, sizes).
Raw file contents and secrets are never forwarded to these helpers.
"""

from __future__ import annotations

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
    """Create and return a new Langfuse root observation (the "trace").

    In Langfuse v4 the first ``start_observation`` on the client is the
    trace root.  Child spans are created by calling ``start_observation``
    on the returned span object.
    """
    client = get_langfuse()
    if client is None:
        return None

    try:
        span = client.start_observation(
            name=name,
            metadata=metadata or {},
        )
        return _SpanWrapper(span)
    except Exception:
        logger.debug("Langfuse trace creation failed; tracing disabled for %s", name)
        return None


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

    When *trace* (a ``_SpanWrapper`` or real LangfuseSpan) is provided the
    new span is created as a child of that trace.  Otherwise it falls back
    to creating a standalone root observation on the client.
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

    # Prefer attaching to the provided parent trace/span.
    target = trace if trace is not None else client

    try:
        # Langfuse v4: start_observation() on client or on a parent span.
        method = getattr(target, "start_observation", None)
        if callable(method):
            span = method(**kwargs)
            return _SpanWrapper(span)
    except Exception:
        logger.debug("Langfuse span creation failed; tracing disabled.", exc_info=True)

    return _NoopSpan()


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
        "as_type": "generation",
        "metadata": metadata or {},
    }
    if model:
        kwargs["model"] = model
    if input_data is not None:
        kwargs["input"] = input_data
    if output is not None:
        kwargs["output"] = output
    if usage:
        kwargs["usage_details"] = usage

    try:
        method = getattr(target, "start_observation", None)
        if callable(method):
            gen = method(**kwargs)
            return _SpanWrapper(gen)
    except Exception:
        logger.debug("Langfuse generation creation failed.", exc_info=True)

    return _NoopSpan()


# ---------------------------------------------------------------------------
# Context-manager wrapper for Langfuse spans
# ---------------------------------------------------------------------------

class _SpanWrapper:
    """Wraps a LangfuseSpan (v4) to add the context-manager protocol.

    Langfuse v4 spans have ``end()`` and ``update()`` but are NOT context
    managers.  This wrapper lets callers use ``with ingestion_span(...)``.
    """

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

    def start_observation(self, **kwargs: Any) -> Any:
        """Create a child observation under this span (Langfuse v4)."""
        try:
            child = self._span.start_observation(**kwargs)
            return _SpanWrapper(child)
        except Exception:
            logger.debug("Langfuse child span creation failed.", exc_info=True)
            return _NoopSpan()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._span, name)


# ---------------------------------------------------------------------------
# Gauge / observation
# ---------------------------------------------------------------------------

def record_gauge(name: str, value: Any, metadata: Optional[dict[str, Any]] = None) -> None:
    """Log an observation against the Langfuse client when present."""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.start_observation(name=name, metadata={"value": value, **(metadata or {})}).end()
    except Exception:
        logger.debug("Langfuse gauge %s failed; ignored.", name)
