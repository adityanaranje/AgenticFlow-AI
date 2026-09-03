from backend.app.core.langfuse import langfuse
from backend.app.db.supabase import get_supabase_admin
from backend.app.rag.qdrant import get_qdrant_client
from backend.app.llm.client import get_openai_client
from backend.app.core.config import settings


def check_openai() -> tuple[bool, str]:
    try:
        client = get_openai_client()

        models = client.models.list()

        if models is None:
            return False, "No response"
        return True, "Connected"
    except Exception as exc:
        return False, str(exc)


def check_supabase() -> tuple[bool, str]:
    try:
        client = get_supabase_admin()

        # Lightweight auth api call that does not depend on our 
        # application tables 
        response = client.auth.admin.list_users(
            page=1,
            per_page=1,
        )

        if response is None:
            return False, "No response"
        return True, "Conected"
    except Exception as exc:
        return False, str(exc)


def check_qdrant() -> tuple[bool, str]:
    try:
        client = get_qdrant_client()

        client.get_collection(
            collection_name=settings.qdrant_collection
        )

        return True, "Connected"
    except Exception as exc:
        return False, str(exc)

def check_langfuse() -> tuple[bool, str]:
    try:
        # Langfuse SDK exposes an auth check.
        authenticated = langfuse.auth_check()

        if authenticated:
            return True, "Connected"
        return False, "Authentication Failed"
    except Exception as exc:
        return False, str(exc)