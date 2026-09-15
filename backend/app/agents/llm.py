"""Small OpenAI chat helper used by the research nodes (Phase 5).

Kept deliberately thin so node functions can accept an injectable ``llm``
callable for tests, while production uses ``chat()`` here. Nothing model- or
provider-specific leaks into the node logic.

Every call is bounded: the OpenAI SDK's default request timeout is 600s, so a
single stalled connection used to look like "research is stuck" for ten
minutes. Transient failures (rate limits, timeouts, 5xx) are retried with
backoff; anything else surfaces immediately, because a malformed request or a
missing key will fail identically on every attempt.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.core.retry import call_with_retries
from app.llm.client import get_openai_client

logger = get_logger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", re.DOTALL)

# Indirection so tests can replace the sleeper without patching global time.
_sleep = time.sleep


class ResearchLLMError(ExternalServiceError):
    """Raised when the model call fails or returns unusable output."""


def _log_retry(attempt: int, exc: BaseException, delay: float) -> None:
    logger.warning(
        "Model call failed (attempt %d): %s — retrying in %.1fs", attempt, exc, delay
    )


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.0,
    max_tokens: int = 2000,
    model: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> str:
    """Run a chat completion and return the assistant text.

    ``timeout`` bounds the HTTP request (default ``OPENAI_TIMEOUT_SECONDS``)
    and ``max_retries`` the number of extra attempts made for transient
    provider errors (default ``RESEARCH_LLM_MAX_RETRIES``).
    """
    client = get_openai_client()
    if client is None:
        raise ResearchLLMError("OpenAI is not configured for research.")

    request_timeout = (
        float(timeout)
        if timeout is not None
        else float(settings.openai_timeout_seconds)
    )
    attempts = max(
        1,
        int(
            max_retries
            if max_retries is not None
            else settings.research_llm_max_retries
        ),
    )

    def _call() -> str:
        response = client.chat.completions.create(
            model=model or settings.openai_chat_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=request_timeout,
        )
        if not response or not response.choices:
            raise ResearchLLMError("Model returned no response.")

        text = (response.choices[0].message.content or "").strip()
        if not text:
            # An empty completion is not a transient condition; retrying it
            # would only spend more tokens.
            raise ResearchLLMError("Model returned an empty response.")
        return text

    try:
        return call_with_retries(
            _call, attempts=attempts, sleep=_sleep, on_retry=_log_retry
        )
    except ResearchLLMError:
        raise
    except Exception as exc:  # network / rate-limit / malformed
        logger.exception("OpenAI chat completion failed.")
        raise ResearchLLMError(f"Model call failed: {exc}") from exc


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
