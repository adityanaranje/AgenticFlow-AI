"""Per-user LLM usage guardrails (Redis-backed).

Stops a single user from burning unbounded model tokens:

    - hourly token quota   LLM_USER_TOKEN_LIMIT_HOURLY   (0 = unlimited)
    - daily token quota    LLM_USER_TOKEN_LIMIT_DAILY    (0 = unlimited)
    - concurrent runs      LLM_USER_MAX_CONCURRENT_RUNS  (0 = unlimited)
    - per-run token budget LLM_RUN_TOKEN_BUDGET (enforced by the worker,
      see app.agents.research_graph._build_services)

Tokens are counted from the *actual* usage returned by the model provider
(estimated from character counts only when the provider omits usage).
Counters live in Redis fixed windows (hour / UTC day), so they reset
themselves via key TTLs — no janitor needed.

Every check degrades to "allowed" when Redis is unavailable (e.g. a bare
dev setup without Redis): guardrails must never break the app when their
storage is down, and the in-process dev fallback is single-user anyway.
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Optional

from app.cache.redis_client import get_redis_client
from app.core.config import settings
from app.core.exceptions import AdmissionError
from app.core.logging import get_logger

logger = get_logger(__name__)

_TOK_HOURLY_PREFIX = "agentflow:tokens:user:{uid}:{hour}:"
_TOK_DAILY_PREFIX = "agentflow:tokens:user:{uid}:{day}:"
_RUN_SET_KEY = "agentflow:runs:user:{uid}"
_RUN_SLOT_KEY = "agentflow:runslot:{uid}:{run_id}"

_HOURLY_TTL = 3600
_DAILY_TTL = 86_400


def _hour_bucket() -> str:
    return str(int(time.time() // _HOURLY_TTL))


def _day_bucket() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")


def _redis():
    client = get_redis_client()
    if client is None:
        return None
    return client


def user_token_usage(user_id: str) -> dict[str, Any]:
    """Current window usage for a user.

    Returns::

        {"hourly": {"used": int, "limit": int},
         "daily":  {"used": int, "limit": int}}

    ``used`` is 0 when Redis is unavailable (limits are then not enforced).
    """
    hourly_limit = max(0, int(settings.llm_user_token_limit_hourly))
    daily_limit = max(0, int(settings.llm_user_token_limit_daily))
    result = {
        "hourly": {"used": 0, "limit": hourly_limit},
        "daily": {"used": 0, "limit": daily_limit},
    }
    client = _redis()
    if client is None:
        return result
    try:
        h_key = _TOK_HOURLY_PREFIX.format(uid=user_id, hour=_hour_bucket())
        d_key = _TOK_DAILY_PREFIX.format(uid=user_id, day=_day_bucket())
        used_h, used_d = client.mget(h_key, d_key)
        result["hourly"]["used"] = int(used_h or 0)
        result["daily"]["used"] = int(used_d or 0)
    except Exception:
        logger.debug("Token usage lookup failed for %s; ignoring.", user_id, exc_info=True)
    return result


def record_user_tokens(user_id: str, tokens: int) -> None:
    """Add real model usage to the user's hourly + daily counters.

    Best-effort: a failed increment logs and moves on (the run continues;
    accounting must not break research).
    """
    tokens = int(tokens or 0)
    if tokens <= 0:
        return
    client = _redis()
    if client is None:
        return
    hourly_limit = max(0, int(settings.llm_user_token_limit_hourly))
    daily_limit = max(0, int(settings.llm_user_token_limit_daily))
    try:
        pipe = client.pipeline()
        if hourly_limit > 0:
            h_key = _TOK_HOURLY_PREFIX.format(uid=user_id, hour=_hour_bucket())
            pipe.incrby(h_key, tokens)
            pipe.expire(h_key, _HOURLY_TTL)
        if daily_limit > 0:
            d_key = _TOK_DAILY_PREFIX.format(uid=user_id, day=_day_bucket())
            pipe.incrby(d_key, tokens)
            pipe.expire(d_key, _DAILY_TTL)
        if hourly_limit > 0 or daily_limit > 0:
            pipe.execute()
    except Exception:
        logger.warning(
            "Failed to record %d tokens for user %s; quota not updated.",
            tokens,
            user_id,
            exc_info=True,
        )


def check_user_quota(user_id: str) -> None:
    """Reject (raise :class:`AdmissionError`) when a token quota is exhausted."""
    usage = user_token_usage(user_id)
    for window in ("hourly", "daily"):
        window_usage = usage[window]
        limit = window_usage["limit"]
        if limit > 0 and window_usage["used"] >= limit:
            raise AdmissionError(
                f"LLM token limit for the {window} window reached "
                f"({window_usage['used']}/{limit} tokens). Please try again later."
            )


# ---------------------------------------------------------------------------
# Concurrent-run slots
# ---------------------------------------------------------------------------

def _run_set_key(user_id: str) -> str:
    return _RUN_SET_KEY.format(uid=user_id)


def _run_slot_key(user_id: str, run_id: str) -> str:
    return _RUN_SLOT_KEY.format(uid=user_id, run_id=run_id)


def _purge_stale_slots(client, user_id: str) -> None:
    """Drop set members whose run-slot key expired (process died mid-run)."""
    run_set = _run_set_key(user_id)
    try:
        members = client.smembers(run_set)
    except Exception:
        return
    for member in members or []:
        try:
            if not client.exists(_run_slot_key(user_id, str(member))):
                client.srem(run_set, member)
        except Exception:
            logger.debug("Stale run-slot cleanup failed for %s.", member, exc_info=True)


def acquire_run_slot(user_id: str, run_id: str) -> None:
    """Reserve one of the user's concurrent-run slots for ``run_id``.

    Atomic enough for this use case: the new run is added, and if that put
    the set over the limit it removes *itself* (never another member) and
    raises. A per-run key with a TTL marks the slot so slots of crashed
    runs are reaped on the next acquisition.
    """
    limit = max(0, int(settings.llm_user_max_concurrent_runs))
    if limit <= 0:
        return  # unlimited
    client = _redis()
    if client is None:
        return  # no Redis → guardrail inactive (dev fallback is single-user)

    run_set = _run_set_key(user_id)
    slot_key = _run_slot_key(user_id, run_id)
    try:
        _purge_stale_slots(client, user_id)
        client.sadd(run_set, run_id)
        client.set(slot_key, "1", ex=max(60, int(settings.research_run_slot_ttl_seconds)))
        count = client.scard(run_set)
        if count > limit:
            client.srem(run_set, run_id)
            client.delete(slot_key)
            raise AdmissionError(
                f"You already have {limit} research run(s) in progress. "
                "Please wait for one to finish before starting another."
            )
    except AdmissionError:
        raise
    except Exception:
        logger.warning(
            "Run-slot acquisition failed for user %s; continuing without the limit.",
            user_id,
            exc_info=True,
        )


def release_run_slot(user_id: str, run_id: str) -> None:
    """Free the user's run slot for ``run_id`` (no-op when absent)."""
    client = _redis()
    if client is None:
        return
    try:
        client.srem(_run_set_key(user_id), run_id)
        client.delete(_run_slot_key(user_id, run_id))
    except Exception:
        logger.debug(
            "Run-slot release failed for user %s run %s (TTL will reap it).",
            user_id,
            run_id,
            exc_info=True,
        )


def admit_research_run(user_id: str, run_id: str) -> None:
    """Full pre-flight admission: token quotas + concurrent-run slot.

    Call after the run row exists (the slot is keyed by the run id), and
    mark the run failed if this raises.
    """
    check_user_quota(user_id)
    acquire_run_slot(user_id, run_id)
