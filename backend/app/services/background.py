"""In-process background work for the API process.

Processing normally runs in the dedicated document worker (``docker compose``
service ``document-worker``) consuming the Redis queue. When Redis is not
configured — a bare ``uvicorn`` dev setup, or a Redis outage — uploads must
still be processed *without* holding the HTTP request open for the whole
pipeline (parse + embeddings + Qdrant + DB writes can take minutes).

:func:`submit` therefore runs the fallback in a small daemon thread pool:
the upload request returns immediately with the document in ``pending``
state, and the client's existing status polling shows the progress, exactly
as it does when the job goes through Redis.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Outstanding tasks, tracked so :func:`wait_idle` can block until the pool is
# genuinely drained (a marker task cannot be used: with more than one worker
# it may run while earlier tasks are still in progress).
_pending = 0
_idle = threading.Condition()


@lru_cache(maxsize=1)
def _pool() -> ThreadPoolExecutor:
    """Lazily created shared pool for fallback ingestion."""
    workers = max(1, int(settings.inline_processing_workers))
    return ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="inline-ingest",
    )


def submit(func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Run ``func`` in the background, logging (never raising) failures."""
    global _pending

    def _run() -> None:
        global _pending
        try:
            func(*args, **kwargs)
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "Background task %s failed.", getattr(func, "__name__", func)
            )
        finally:
            with _idle:
                _pending -= 1
                _idle.notify_all()

    with _idle:
        _pending += 1
    try:
        _pool().submit(_run)
    except Exception:
        with _idle:
            _pending -= 1
            _idle.notify_all()
        raise


def wait_idle(timeout: float | None = None) -> bool:
    """Block until every submitted background task finished.

    Returns ``True`` when the pool drained within ``timeout`` seconds.
    Used by tests and by shutdown paths that need a clean point in time.
    """
    with _idle:
        return _idle.wait_for(lambda: _pending == 0, timeout=timeout)


def shutdown(wait: bool = True) -> None:
    """Stop accepting background work (used on application shutdown)."""
    if _pool.cache_info().currsize:  # only shut down a pool that was created
        _pool().shutdown(wait=wait)
        _pool.cache_clear()
