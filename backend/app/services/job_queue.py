"""Redis-backed job queue for document processing (Phase 4, §6).

Jobs are simple JSON messages pushed onto a Redis list; the worker
(:mod:`app.workers.document_worker`) consumes them with ``blpop``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable

from app.cache.redis_client import get_redis_client
from app.core.config import settings
from app.core.logging import get_logger
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = get_logger(__name__)

QUEUE_NAME = settings.document_job_queue
RESEARCH_QUEUE = settings.research_job_queue


def _push(queue: str, payload: dict) -> bool:
    client = get_redis_client()
    if client is None:
        logger.warning("Redis is not configured; job NOT enqueued (%s).", queue)
        return False
    try:
        client.rpush(queue, json.dumps(payload))
        return True
    except Exception:
        logger.exception("Failed to enqueue job on %s", queue)
        return False


def _pop(queue: str, timeout: int = 0) -> dict | None:
    client = get_redis_client()
    if client is None:
        return None
    try:
        item = client.blpop([queue], timeout=timeout)
        if not item:
            return None
        _, raw = item
        return json.loads(raw)
    except RedisTimeoutError:
        # Expected while idle: the client's socket read timeout (3s) is
        # shorter than the BLPOP block window, so an empty wait surfaces as
        # a socket TimeoutError — it only means "no job arrived yet".
        return None
    except Exception:
        logger.exception("Failed to pop a job from %s", queue)
        return None


def pop_with_backoff(
    pop: Callable[..., str | None], timeout: int = 2
) -> str | None:
    """Pop the next job, sleeping when the underlying pop could not block.

    With Redis configured the BLPOP itself waits ``timeout`` seconds, so an
    empty queue returns after that wait. Without Redis, ``pop`` returns
    immediately — and a consumer loop that never blocks would spin at full
    CPU on every worker thread, so the wait is applied explicitly when the
    call came back too fast to have blocked.

    Keep ``timeout`` below the Redis client's socket read timeout (3s in
    :mod:`app.cache.redis_client`) so an idle queue stays quiet.
    """
    started = time.monotonic()
    job = pop(timeout=timeout)
    if job is None and (time.monotonic() - started) < 0.1:
        time.sleep(timeout)
    return job


def enqueue_document(document_id: str) -> bool:
    """Enqueue a document for background processing.

    Returns ``True`` when queued, ``False`` when Redis is unavailable.
    """
    ok = _push(QUEUE_NAME, {"document_id": document_id})
    if ok:
        logger.info("Enqueued document %s for processing.", document_id)
    else:
        logger.warning("Could not enqueue document %s.", document_id)
    return ok


def pop_next_document(timeout: int = 0) -> str | None:
    payload = _pop(QUEUE_NAME, timeout=timeout)
    if not payload:
        return None
    return str(payload.get("document_id", "")) or None


def _research_payload(research_id: str) -> dict:
    """The queue message for one research run (single source of truth)."""
    return {"research_id": research_id}


def enqueue_research(research_id: str) -> bool:
    """Enqueue a research run for background execution."""
    ok = _push(RESEARCH_QUEUE, _research_payload(research_id))
    if ok:
        logger.info("Enqueued research %s.", research_id)
    else:
        logger.warning("Could not enqueue research %s.", research_id)
    return ok


def pop_next_research(timeout: int = 0) -> str | None:
    payload = _pop(RESEARCH_QUEUE, timeout=timeout)
    if not payload:
        return None
    return str(payload.get("research_id", "")) or None


def claim_research(research_id: str) -> bool:
    """Take an unclaimed research job back off the queue.

    Used by the API process when no worker picked a job up (a bare ``uvicorn``
    dev setup, or a worker that is down): the run would otherwise sit in
    ``queued`` forever. ``LREM`` matches the exact payload that was pushed and
    is atomic, so a job is either removed here (``True`` — the caller may run
    it in-process) or was already popped by a worker (``False``, nothing to
    do). It can never be executed twice.
    """
    client = get_redis_client()
    if client is None:
        return False
    raw = json.dumps(_research_payload(research_id))
    try:
        return bool(client.lrem(RESEARCH_QUEUE, 1, raw))
    except Exception:
        logger.exception("Failed to claim the unclaimed research job %s", research_id)
        return False

# Backwards-compatible alias used by the document worker tests.
pop_next = pop_next_document
