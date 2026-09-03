from langchain_openai import ChatOpenAI
from backend.app.core.config import settings

def get_chat_model(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.openai_api_key,
        model=settings.openai_chat_model,
        temperature=temperature,
    )