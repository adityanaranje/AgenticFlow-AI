from functools import lru_cache
from supabase import Client, create_client
from backend.app.core.config import settings

@lru_cache
def get_supabase_admin() -> Client:
    """
    Server-side Supabase client.
    WARNING:
    Uses the service role key and therefore bypass RLS.
    Never expose this client or key to the frontend.
    """
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )