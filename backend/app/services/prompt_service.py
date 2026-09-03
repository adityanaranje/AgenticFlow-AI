from backend.app.core.langfuse import langfuse

def get_production_prompt(name: str):
    """
    Retrieve the prompt version carrying the 'production' lable.
    
    Langfuse caches prompts client-side, so this does not 
    require a network request for every agent invocation.
    """

    return langfuse.get_prompt(
        name = name,
        lable = "production"
    )