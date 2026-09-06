from app.core.config import settings
from langchain_openai import ChatOpenAI


def get_chat_model(temperature: float = 0.0) -> ChatOpenAI:
    """Return the configured OpenAI chat model via LangChain."""
    return ChatOpenAI(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        temperature=temperature,
    )


def get_embeddings_model():
    """Return the configured OpenAI embeddings model via LangChain."""
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        api_key=settings.openai_api_key,
        model=settings.openai_embedding_model,
    )
