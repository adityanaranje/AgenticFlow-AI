"""OpenAI embedding generation (Phase 4, §9).

The embedding model is fully configurable via ``OPENAI_EMBEDDING_MODEL``;
the Qdrant collection dimension must match that model (``EMBEDDING_DIMENSIONS``)
— see :mod:`app.services.vector_store`. Nothing here hard-codes a dimension;
callers use :func:`settings.embedding_dimensions` to configure Qdrant.

Large ingestions embed thousands of chunks. Doing that one small request at
a time is the single biggest contributor to "uploading takes forever", so
:func:`embed_texts_batched` splits the work into provider-friendly batches and
runs a bounded number of them concurrently (see ``EMBEDDING_BATCH_SIZE`` /
``EMBEDDING_CONCURRENCY``), retrying transient failures with backoff.
"""

from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.core.config import settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.llm.client import get_openai_client

logger = get_logger(__name__)

# Provider-side hiccups that are safe to retry: rate limits, timeouts,
# connection resets and 5xx responses. Everything else (bad request, auth,
# quota exhausted) is raised immediately — retrying cannot fix it.
_RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}

# Indirection so tests (and future async runtimes) can replace the sleeper
# without patching the global ``time`` module.
_sleep = time.sleep


def _client():
    client = get_openai_client()
    if client is None:
        raise ConfigurationError(
            "OpenAI is not configured; cannot generate embeddings."
        )
    return client


def _is_retryable(exc: BaseException) -> bool:
    """Whether ``exc`` looks like a transient provider error."""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status in _RETRYABLE_STATUS_CODES:
        return True
    # openai SDK exception class names are stable across versions; matching
    # on the name keeps this working with SDK builds whose module layout
    # differs (and avoids importing a private error hierarchy).
    name = type(exc).__name__
    return name in {
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
        "APIStatusError",
    }


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts (batched by the API) and return them in order."""
    if not texts:
        return []
    cleaned = [text[:8000] for text in texts]
    client = _client()
    response = client.embeddings.create(
        model=settings.openai_embedding_model,
        input=cleaned,
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    return [list(item.embedding) for item in ordered]


def _embed_batch(texts: list[str], attempts: int) -> list[list[float]]:
    """Embed one batch, retrying transient failures with exponential backoff."""
    last_error: BaseException | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return embed_texts(texts)
        except Exception as exc:  # noqa: BLE001 - re-raised below when fatal
            last_error = exc
            if attempt >= attempts or not _is_retryable(exc):
                raise
            # Exponential backoff with jitter (0.5s, 1s, 2s, ... capped at 8s).
            delay = min(8.0, 0.5 * (2 ** (attempt - 1))) * (0.5 + random.random())
            logger.warning(
                "Embedding batch failed (attempt %d/%d, %d texts): %s — retrying in %.1fs",
                attempt,
                attempts,
                len(texts),
                exc,
                delay,
            )
            _sleep(delay)
    raise last_error  # pragma: no cover - loop always returns or raises


def embed_texts_batched(
    texts: list[str],
    *,
    batch_size: int | None = None,
    concurrency: int | None = None,
    max_retries: int | None = None,
) -> list[list[float]]:
    """Embed many texts in batches, concurrently, preserving input order.

    ``batch_size`` texts go into each OpenAI request (a larger batch means
    fewer round trips); up to ``concurrency`` requests are in flight at once
    (embeddings are pure I/O wait, so this scales nearly linearly until the
    provider's rate limit is reached, where :func:`_embed_batch` backs off).
    """
    if not texts:
        return []

    size = max(1, int(batch_size or settings.embedding_batch_size))
    workers = max(1, int(concurrency or settings.embedding_concurrency))
    attempts = max(1, int(max_retries or settings.embedding_max_retries))

    batches = [texts[start : start + size] for start in range(0, len(texts), size)]

    # A single batch (small documents) needs no thread pool at all.
    if len(batches) == 1 or workers == 1:
        return [vector for batch in batches for vector in _embed_batch(batch, attempts)]

    results: list[list[list[float]]] = [[] for _ in batches]
    futures: dict[Any, int] = {}
    failed = False
    pool = ThreadPoolExecutor(
        max_workers=min(workers, len(batches)),
        thread_name_prefix="embed",
    )
    try:
        futures = {
            pool.submit(_embed_batch, batch, attempts): index
            for index, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    except BaseException:
        # Fail fast: a fatal provider error must not wait for the remaining
        # batches (the document is marked failed and can be reprocessed).
        failed = True
        for future in futures:
            future.cancel()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=failed)

    return [vector for batch in results for vector in batch]


def embed_query(query: str) -> list[float]:
    """Embed a single query string (used for retrieval)."""
    vectors = embed_texts([query])
    return vectors[0]


def embedding_dimension() -> int:
    """The configured vector dimension for the chosen embedding model."""
    return settings.embedding_dimensions
