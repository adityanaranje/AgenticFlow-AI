from functools import lru_cache
from typing import Optional

from qdrant_client import QdrantClient
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

@lru_cache(maxsize=1)
def get_qdrant_client() -> Optional[QdrantClient]:
    """Return the configured Qdrant Cloud client."""

    if not settings.qdrant_url:
        logger.warning("QDRANT_URL is not configured.")
        return None

    try:
        return QdrantClient(
            url = settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=30,
        )
    except Exception:
        logger.exception("Failed to initialize Qdrant client.")
        return None