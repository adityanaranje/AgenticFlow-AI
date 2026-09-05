from typing import Optional

from langfuse import Langfuse

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_langfuse: Optional[Langfuse] = None

def get_langfuse() -> Optional[Langfuse]:
    """
    Return the Langfuse client
    """

    global _langfuse

    if _langfuse is not None:
        return _langfuse

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning("Langfuse credentials are not configured.")
        return None

    try:
        _langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host = settings.langfuse_base_url,
        )

        return _langfuse
    except Exception:
        logger.exception("Failed to initialize Langfuse.")
        return None

def flush_langfuse() -> None:
    """Flush pending Langfuse events"""

    client = get_langfuse()

    if client is None:
        return
    try:
        client.flush()
    except Exception:
        logger.exception("Failed to flush Langfuse events.")