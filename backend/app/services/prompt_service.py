from app.core.langfuse import get_langfuse


def get_production_prompt(name: str):
    """Retrieve the Langfuse prompt version labeled ``production``.

    Langfuse caches prompts client-side, so this does not require a
    network request for every agent invocation.
    """
    client = get_langfuse()

    if client is None:
        return None

    return client.get_prompt(
        name=name,
        label="production",
    )
