"""Small OpenAI chat helper used by the research nodes (Phase 5).

Kept deliberately thin so node functions can accept an injectable ``llm``
callable for tests, while production uses ``chat()`` here. Nothing model- or
provider-specific leaks into the node logic.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.llm.client import get_openai_client

logger = get_logger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", re.DOTALL)


class ResearchLLMError(ExternalServiceError):
    """Raised when the model call fails or returns unusable output."""


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.0,
    max_tokens: int = 2000,
    model: Optional[str] = None,
) -> str:
    """Run a chat completion and return the assistant text."""
    client = get_openai_client()
    if client is None:
        raise ResearchLLMError("OpenAI is not configured for research.")

    try:
        response = client.chat.completions.create(
            model=model or settings.openai_chat_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # network / rate-limit / malformed
        logger.exception("OpenAI chat completion failed.")
        raise ResearchLLMError(f"Model call failed: {exc}") from exc

    if not response or not response.choices:
        raise ResearchLLMError("Model returned no response.")

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise ResearchLLMError("Model returned an empty response.")

    return text


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from model text (tolerating fences)."""
    candidate = text.strip()
    match = _FENCE.search(text)
    if match:
        candidate = match.group(1).strip()
    # Fall back to the outermost { ... } block.
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ResearchLLMError(f"Model did not return valid JSON: {exc}") from exc


def parse_list(text: str) -> list[str]:
    """Parse a numbered/bulleted list from model text into strings."""
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # strip leading numbering/bullets
        cleaned = re.sub(r"^([\d\w]+[.)\]\-*•]|[-*])\s+", "", line)
        if cleaned:
            items.append(cleaned)
    return items
