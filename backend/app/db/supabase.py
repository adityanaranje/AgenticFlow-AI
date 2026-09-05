from functools import lru_cache
from typing import Optional

from supabase import Client, create_client
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

@lru_cache(maxsize= 1)
def get_supabase() -> Optional[Client]:
    """
    Create the server-side Supabase client.
    The service-role key is intentionally backend-only.
    """

    if not settings.supabase_url:
        logger.warning("SUPABASE_URL is not configured.")
        return None

    if not settings.supabase_service_role_key:
        logger.warning("SUPABASE_SERVICE_ROLE_KEY is not congiured.")
        return None

    try:
        return create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    except Exception:
        logger.exception("Failed to initialize Supabase.")
        return None