"""Lightweight Langfuse tracing helpers for the ingestion pipeline.

Used to instrument document processing, parsing, chunking, embedding,
vector insertion and retrieval. Every helper degrades to a no-op when
Langfuse is not configured (or the installed SDK differs), so tracing never
blocks ingestion.

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


def ingestion_span(
    name: str,
    *,
    metadata: Optional[dict[str, Any]] = None,
    input_data: Any = None,
) -> Any:
    """Return a context-managed Langfuse span for ``name`` (no-op if absent)."""
    client = get_langfuse()
    if client is None:
        return _NoopSpan()

    kwargs: dict[str, Any] = {
        "name": name,
        "metadata": metadata or {},
    }
    if input_data is not None:
        kwargs["input"] = input_data

    # langfuse v2 exposes `.span(...)`; v3 exposes `.start_span(...)`. Try both
    # and fall back to a no-op so a minor SDK mismatch cannot break ingestion.
    for method_name in ("start_span", "span"):
        method = getattr(client, method_name, None)
        if not callable(method):
            continue
        try:
            span = method(**kwargs)
            if hasattr(span, "__enter__"):
                return span
        except Exception:
            logger.debug("Langfuse %s failed; tracing disabled.", method_name)
            break

    return _NoopSpan()


def record_gauge(name: str, value: Any, metadata: Optional[dict[str, Any]] = None) -> None:
    """Log an observation against the Langfuse client when present."""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.span(name=name, metadata={"value": value, **(metadata or {})})
    except Exception:
        logger.debug("Langfuse gauge %s failed; ignored.", name)
