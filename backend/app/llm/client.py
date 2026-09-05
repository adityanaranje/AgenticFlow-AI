from functools import lru_cache
from typing import Optional
from openai import OpenAI
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

@lru_cache(maxsize=1)
def get_openai_client() -> Optional[OpenAI]:
    """Return the configured OpenAI client."""

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY is not configured.")
        return None

    try:
        return OpenAI(api_key= settings.openai_api_key)
    
    except Exception:
        logger.exception("Failed to initialize OpenAI client.")
        return None