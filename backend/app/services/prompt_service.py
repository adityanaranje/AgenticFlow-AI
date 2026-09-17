"""Centralized prompt management backed by Langfuse Prompt Management.

Every system prompt in the platform is versioned in Langfuse and fetched
through this module, so prompts can be iterated on in the Langfuse UI (or
via the SDK) without shipping a new release. ``PROMPTS.md`` at the
repository root documents the prompt catalog and the setup steps.

This module uses the current, non-deprecated Langfuse Python SDK prompt
API (SDK v3/v4, OpenTelemetry-based):

    prompt = client.get_prompt(name=..., type="text", label="production")
    text = prompt.compile(**variables)

- ``label="production"`` fetches the version labeled *production* — the
  version the UI serves by default.
- The SDK caches fetched prompts client-side (TTL via
  ``PROMPT_CACHE_TTL_SECONDS``, default 60s; set 0 in development to
  always fetch the latest version), so this is not a network call per
  invocation.
- Templates use ``{{double_brace}}`` variables, filled in with
  ``prompt.compile(**variables)``. Literal single braces (JSON examples in
  the prompt bodies) are untouched, which is why the old ``str.format``
  hack in the planner is no longer needed.

Resilience: when Langfuse is not configured, a prompt does not exist in
Langfuse yet, or the fetch fails, the in-code fallback from
:mod:`app.agents.prompts` is used so the research pipeline never stops
because of prompt management.

Tracing: the returned :class:`ManagedPrompt` keeps the Langfuse
``PromptClient`` when the text came from Langfuse. Nodes wrap their model
calls in ``app.core.observability.prompt_scope(prompt)`` so the
corresponding generations in Langfuse carry the prompt name + version
(the "Prompt Name" column in the UI).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from app.core.config import settings
from app.core.langfuse import get_langfuse
from app.core.logging import get_logger

logger = get_logger(__name__)

# ``{{variable}}`` placeholders (Langfuse template syntax) in fallback text.
_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class ManagedPrompt:
    """A resolved system prompt.

    Attributes:
        name: Langfuse prompt name the text was (attempted to be) served
            from, e.g. ``research-planner``.
        text: The compiled prompt text, ready to use as a system message.
        client: The Langfuse ``PromptClient`` (exposes ``name``/``version``)
            when the text was served by Langfuse — used to link the prompt
            to generations in traces. ``None`` when the in-code fallback
            was used (fallbacks are never linked).
    """

    name: str
    text: str
    client: Optional[Any] = None

    @property
    def version(self) -> Optional[int]:
        version = getattr(self.client, "version", None)
        return int(version) if version is not None else None


def _render_fallback(template: str, variables: Optional[dict[str, Any]]) -> str:
    """Fill known ``{{var}}`` placeholders in an in-code fallback template.

    Unknown placeholders are left intact so a missing variable is visible
    in the prompt instead of silently becoming an empty string.
    """
    if not variables:
        return template

    def _sub(match: re.Match) -> str:
        key = match.group(1)
        if key in variables:
            return str(variables[key])
        return match.group(0)

    return _VAR_RE.sub(_sub, template)


def get_system_prompt(
    name: str,
    *,
    fallback: str,
    variables: Optional[dict[str, Any]] = None,
) -> ManagedPrompt:
    """Return the production version of a Langfuse text prompt.

    Args:
        name: Langfuse prompt name (e.g. ``research-planner``).
        fallback: in-code template used when Langfuse is unavailable —
            keeps the pipeline running with a known-good prompt.
        variables: values for ``{{var}}`` placeholders, e.g.
            ``{"max_subquestions": 5}``.

    Returns:
        A :class:`ManagedPrompt`; use ``.text`` for the system message and
        pass the object to ``prompt_scope`` around the model call.
    """
    client = get_langfuse()
    if client is None:
        return ManagedPrompt(name=name, text=_render_fallback(fallback, variables))

    try:
        prompt = client.get_prompt(
            name=name,
            type="text",
            label="production",
            cache_ttl_seconds=settings.prompt_cache_ttl_seconds,
        )
        return ManagedPrompt(
            name=name,
            text=prompt.compile(**(variables or {})),
            client=prompt,
        )
    except Exception:
        logger.warning(
            "Could not fetch Langfuse prompt '%s' (production); "
            "using the in-code fallback.",
            name,
            exc_info=True,
        )
        return ManagedPrompt(name=name, text=_render_fallback(fallback, variables))
