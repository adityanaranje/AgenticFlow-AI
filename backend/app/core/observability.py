"""Lightweight Langfuse tracing helpers for the ingestion and research pipelines.

Every helper degrades to a no-op when Langfuse is not configured (or the
installed SDK differs), so tracing never blocks ingestion or research.

Langfuse v4 (the installed version) uses an observation-based API:

    - ``client.start_observation()`` creates a root span (the "trace").
    - ``client.start_as_current_observation()`` creates a span that becomes
      the *active* OpenTelemetry span, so observations created deeper in
      the call stack (e.g. LLM generations from ``app.agents.llm.chat``)
      nest under it automatically.
    - ``as_type`` controls the observation kind (span, generation, etc).
    - ``propagate_attributes()`` links trace-level attributes — most
      importantly the ``production`` prompt (``prompt``) and ``user_id`` —
      to every observation created within its context.  The prompt link is
      what fills Langfuse UI's "Prompt Name" column on generations.

Privacy: span inputs/outputs carry only summaries (ids, questions,
counts, sizes) — never secrets. LLM *generations* do carry the actual
model messages, which is the point of tracing them (the app operator's
own Langfuse project is the intended store for this data).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Optional

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
# Current-scope observations (Langfuse v4)
# ---------------------------------------------------------------------------

def _propagate_attributes() -> Any:
    """The SDK's ``propagate_attributes`` function, or ``None`` if the
    installed SDK does not provide it."""
    try:
        from langfuse import propagate_attributes

        return propagate_attributes
    except Exception:
        return None


def current_observation(
    name: str,
    *,
    metadata: Optional[dict[str, Any]] = None,
    input_data: Any = None,
    as_type: str = "span",
) -> Any:
    """Context manager for an observation that becomes the ACTIVE span.

    Unlike :func:`ingestion_span` (which links children explicitly through
    the wrapper), this uses the SDK's ``start_as_current_observation``, so
    observations created deeper in the call stack — most importantly the
    LLM generations recorded by ``app.agents.llm.chat`` — attach under it
    automatically (including from ThreadPoolExecutor workers, which copy
    the current context).

    Yields a span object supporting ``.update(**kwargs)`` (input, output,
    metadata, level, ...). Degrades to a no-op context manager when
    Langfuse is unavailable or the SDK predates this API.
    """
    client = get_langfuse()
    start = getattr(client, "start_as_current_observation", None)
    if client is None or not callable(start):
        return _NoopSpan()

    kwargs: dict[str, Any] = {"name": name}
    if as_type != "span":
        kwargs["as_type"] = as_type
    if metadata:
        kwargs["metadata"] = metadata
    if input_data is not None:
        kwargs["input"] = input_data

    try:
        return start(**kwargs)
    except Exception:
        logger.debug("Langfuse observation creation failed for %s", name, exc_info=True)
        return _NoopSpan()


@contextmanager
def user_scope(user_id: Optional[str] = None) -> Iterator[None]:
    """Propagate a trace-level ``user_id`` to every observation created
    within this scope (Langfuse v4 ``propagate_attributes``).

    This is what fills the "User" column of the Langfuse trace list. No-op
    when there is no user, Langfuse is unavailable, or the SDK predates
    the API.
    """
    if user_id is None:
        yield
        return

    propagate = _propagate_attributes()
    if propagate is None:
        yield
        return

    from contextlib import ExitStack

    with ExitStack() as stack:
        try:
            stack.enter_context(propagate(user_id=str(user_id)[:200]))
        except Exception:
            logger.debug("Langfuse user propagation failed; continuing.")
        yield


@contextmanager
def prompt_scope(prompt: Any) -> Iterator[Any]:
    """Link a managed prompt to the generations created within this scope.

    ``prompt`` is a ``ManagedPrompt`` from
    :mod:`app.services.prompt_service`. When its text was served by
    Langfuse, the ``PromptClient`` (name + version) is passed to
    ``propagate_attributes(prompt=...)`` so the Langfuse UI "Prompt Name"
    column shows exactly which prompt version each model call used.
    Fallback prompts (``client is None``) are never linked.
    """
    client = getattr(prompt, "client", None)
    if client is None:
        yield client
        return

    propagate = _propagate_attributes()
    if propagate is None:
        yield client
        return

    from contextlib import ExitStack

    with ExitStack() as stack:
        try:
            stack.enter_context(propagate(prompt=client))
        except Exception:
            logger.debug(
                "Langfuse prompt propagation failed; continuing without prompt link."
            )
        yield client


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
