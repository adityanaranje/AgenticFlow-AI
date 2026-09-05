from functools import lru_cache
from typing import Optional

import redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

@lru_cache(maxsize=1)
def get_redis_client() -> Optional[redis.Redis]:
    """
    Return the Redis client.
    """

    if not settings.redis_url:
        logger.warning("REDIS_URL is not configured.")
        return None

    try:
        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        return client
    except Exception:
        logger.exception("Failed to initialize Redis client.")
        return None

def ping_redis() -> bool:
    """Check Redis connectivity"""
    client = get_redis_client()

    if client is None:
        return False

    try:
        return bool(client.ping())
    except Exception:
        logger.exception("Redis ping failed.")
        return False
