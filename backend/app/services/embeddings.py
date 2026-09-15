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

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.cache.redis_client import get_redis_client
from app.core.config import settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.core.retry import call_with_retries, is_retryable_error
from app.llm.client import get_openai_client

logger = get_logger(__name__)

# Indirection so tests (and future async runtimes) can replace the sleeper
# without patching the global ``time`` module.
_sleep = time.sleep

# Query embeddings are a pure function of (model, text), so caching them can
# never return a stale answer — unlike cached retrieval results, which go
# stale as soon as documents are uploaded. Research runs re-ask the same
# question (and its sub-questions) across iterations and re-runs.
_CACHE_PREFIX = "agentflow:embed:query:"


def _client():
    client = get_openai_client()
    if client is None:
        raise ConfigurationError(
            "OpenAI is not configured; cannot generate embeddings."
        )
    return client


def _is_retryable(exc: BaseException) -> bool:
    """Whether ``exc`` looks like a transient provider error (see core.retry)."""
    return is_retryable_error(exc)


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


def _log_retry(batch_size: int):
    """Build the ``on_retry`` logger for one embedding batch."""

    def _on_retry(attempt: int, exc: BaseException, delay: float) -> None:
        logger.warning(
            "Embedding batch failed (attempt %d, %d texts): %s — retrying in %.1fs",
            attempt,
            batch_size,
            exc,
            delay,
        )

    return _on_retry


def _embed_batch(texts: list[str], attempts: int) -> list[list[float]]:
    """Embed one batch, retrying transient failures with exponential backoff."""
    return call_with_retries(
        lambda: embed_texts(texts),
        attempts=attempts,
        sleep=_sleep,
        on_retry=_log_retry(len(texts)),
    )


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


def _cache_key(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}{settings.openai_embedding_model}:{digest}"


def _cache_get(text: str) -> list[float] | None:
    """Return a cached query vector, or ``None`` (best effort)."""
    if not settings.embedding_cache_enabled:
        return None
    client = get_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(_cache_key(text))
    except Exception:
        logger.debug("Embedding cache read failed; ignoring.", exc_info=True)
        return None
    if not raw:
        return None
    try:
        vector = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(vector, list) or not vector:
        return None
    return [float(value) for value in vector]


def _cache_set(text: str, vector: list[float]) -> None:
    """Store a query vector for later runs (best effort)."""
    if not settings.embedding_cache_enabled or not vector:
        return
    client = get_redis_client()
    if client is None:
        return
    try:
        client.set(
            _cache_key(text),
            json.dumps([round(float(value), 8) for value in vector]),
            ex=max(1, int(settings.embedding_cache_ttl_seconds)),
        )
    except Exception:
        logger.debug("Embedding cache write failed; ignoring.", exc_info=True)


def embed_query(query: str) -> list[float]:
    """Embed a single query string (used for retrieval).

    Identical query text is served from the cache when Redis is configured:
    a research run re-embeds its question and sub-questions on every
    iteration and re-run, and the vector for a given text can never change.
    """
    cached = _cache_get(query)
    if cached is not None:
        return cached

    vectors = embed_texts([query])
    vector = vectors[0]
    _cache_set(query, vector)
    return vector


def embedding_dimension() -> int:
    """The configured vector dimension for the chosen embedding model."""
    return settings.embedding_dimensions
