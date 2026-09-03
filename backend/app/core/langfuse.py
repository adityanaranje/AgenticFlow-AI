import os
from langfuse import get_client
from backend.app.core.config import settings

def configure_langfuse() -> None:
    """
    Langfuse SDK reads its credentials from environment variables.
    Normalize our application configuration for the SDK.
    """

    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_BASE_URL"] = settings.langfuse_base_url

configure_langfuse()

langfuse = get_client()