from functools import lru_cache
from openai import OpenAI
from backend.app.core.config import settings

@lru_cache
def get_openai_client() -> OpenAI:
    return OpenAI(
        api_key=settings.openai_api_key
    )