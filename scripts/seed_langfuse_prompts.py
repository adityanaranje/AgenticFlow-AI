#!/usr/bin/env python3
"""Seed the AgentFlow AI prompts into Langfuse Prompt Management.

Creates every system prompt used by the platform in your Langfuse project,
labeled ``production`` so the backend serves them immediately. Idempotent:
prompts that already exist in Langfuse are left untouched (the Langfuse UI
is the source of truth once a prompt exists). Use ``--force`` to publish a
new ``production`` version from the in-code defaults.

This uses the current, non-deprecated Langfuse Python SDK API (v3/v4):

    client.create_prompt(name=..., prompt=..., type="text",
                         labels=["production"], config={...})

(``is_active=True`` is deprecated in the SDK — the ``production`` label
replaces it, and it is what the backend fetches at runtime.)

Prerequisites (see ``PROMPTS.md`` for the full walkthrough):

    LANGFUSE_HOST=https://cloud.langfuse.com   # or your self-hosted URL
    LANGFUSE_PUBLIC_KEY=pk-lf-...
    LANGFUSE_SECRET_KEY=sk-lf-...

Usage (from the repository root, with the backend venv active)::

    python scripts/seed_langfuse_prompts.py             # create missing prompts
    python scripts/seed_langfuse_prompts.py --force     # republish all from code
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from app.agents import prompts  # noqa: E402
from app.core.config import get_settings  # noqa: E402

# (Langfuse prompt name, in-code fallback template, used by)
PROMPTS = (
    (
        "research-planner",
        prompts.PLANNER_SYSTEM,
        "planner node (variable: max_subquestions)",
    ),
    (
        "research-query-rewriter",
        prompts.RETRIEVER_QUERY_SYSTEM,
        "reserved (retriever is currently deterministic)",
    ),
    (
        "research-evidence-extractor",
        prompts.EVIDENCE_SYSTEM,
        "evidence analyzer node",
    ),
    (
        "research-gap-detector",
        prompts.GAP_SYSTEM,
        "gap detector node",
    ),
    (
        "research-report-synthesis",
        prompts.SYNTHESIS_SYSTEM,
        "synthesis node",
    ),
    (
        "research-citation-validator",
        prompts.VALIDATOR_SYSTEM,
        "reserved (validator is currently deterministic)",
    ),
    (
        "report-quality-judge",
        prompts.EVALUATION_JUDGE_SYSTEM,
        "report evaluation (LLM answer-quality score)",
    ),
)


def _existing(client, name: str):
    """Return the prompt client if ``name`` exists in Langfuse, else None."""
    try:
        return client.get_prompt(name=name, type="text", label="production")
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force",
        action="store_true",
        help="Publish a new production version from the in-code defaults, "
        "even when the prompt already exists in Langfuse.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        print(
            "LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set.\n"
            "Add them to your .env (see PROMPTS.md) and retry.",
            file=sys.stderr,
        )
        return 1

    from langfuse import Langfuse

    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    if not client.auth_check():
        print(
            "Langfuse auth check failed — check LANGFUSE_HOST and the keys.",
            file=sys.stderr,
        )
        return 1

    created = skipped = 0
    for name, template, used_by in PROMPTS:
        existing = None if args.force else _existing(client, name)
        if existing is not None:
            labels = ",".join(sorted(existing.labels or []))
            print(f"skip    {name}  (v{existing.version}, labels: {labels})")
            skipped += 1
            continue
        prompt = client.create_prompt(
            name=name,
            prompt=template,
            type="text",
            labels=["production"],
            config={
                "model": settings.openai_chat_model,
                "temperature": 0,
            },
        )
        print(f"created {name}  (v{prompt.version}, production) — {used_by}")
        created += 1

    client.flush()

    print(
        f"\nDone: {created} created, {skipped} already present in Langfuse "
        f"({settings.langfuse_host}).\n"
        "The backend now serves these prompts; the in-code fallback in "
        "backend/app/agents/prompts.py is only used if a fetch fails."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
