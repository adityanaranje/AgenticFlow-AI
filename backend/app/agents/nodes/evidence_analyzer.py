"""Evidence analyzer node (Phase 5, §5/§8).

Retrieved chunks are analysed in batches and the claims are merged. Sending
every chunk in one prompt was both a latency and a correctness problem: the
retriever can hand over hundreds of chunks, and a single prompt of that size
exceeds the model's context window — the call fails and the run silently
falls back to flat, unanalysed evidence. Batching keeps each prompt within
``EVIDENCE_BATCH_CHARS``, lets the batches be analysed in parallel, and
guarantees every claim is still tied to the chunk it came from.

Source labels are global (``source:<index>`` into ``state.retrieved``), so
merging batches keeps claims mapped to the exact chunk that supports them.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.agents import prompts
from app.agents.context import ResearchServices
from app.agents.llm import parse_json_object
from app.agents.state import EvidenceItem, ResearchState, RetrievedChunk
from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import prompt_scope
from app.services.prompt_service import get_system_prompt

logger = get_logger(__name__)

# Characters of each chunk sent to the model as an excerpt.
_EXCERPT_CHARS = 3000


def _source_label(index: int) -> str:
    return f"source:{index}"


def _evidence_from_chunk(chunk: RetrievedChunk, claim: str, confidence: float) -> EvidenceItem:
    page = f"p.{chunk.page_number}" if chunk.page_number else ""
    source = " ".join(
        part for part in [chunk.filename or "document", page] if part
    )
    return EvidenceItem(
        claim=claim,
        supporting_source=source,
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        supporting_chunk=chunk.content,
        confidence=confidence,
        filename=chunk.filename,
        page_number=chunk.page_number,
        chunk_index=chunk.chunk_index,
    )


def _fallback_evidence(state: ResearchState) -> list[EvidenceItem]:
    """Deterministic grounding fallback when the model output is unusable.

    Never fabricates: claims are bounded to actual retrieved chunk text, with
    confidence derived from the retrieval score, not the model.
    """
    evidence: list[EvidenceItem] = []
    for i, chunk in enumerate(state.retrieved):
        first_sentence = chunk.content.strip().split("\n")[0][:300]
        confidence = max(0.3, min(0.95, chunk.score)) if chunk.score else 0.5
        evidence.append(
            _evidence_from_chunk(chunk, claim=first_sentence, confidence=confidence)
        )
    return evidence


def _select_chunks(indexed: list[tuple[int, RetrievedChunk]]) -> list[tuple[int, RetrievedChunk]]:
    """Keep the most relevant chunks, in retrieval order.

    Beyond ``EVIDENCE_MAX_CHUNKS`` the prompt cost grows without adding
    coverage, and a model asked to cite hundreds of excerpts tends to return
    malformed JSON (which costs the whole analysis). Selection uses the
    retrieval score — the only relevance signal available — and the surviving
    chunks keep their original order and global source indices.
    """
    limit = max(1, int(settings.evidence_max_chunks))
    if len(indexed) <= limit:
        return indexed
    keep = {
        index
        for index, _ in sorted(
            indexed, key=lambda pair: pair[1].score or 0.0, reverse=True
        )[:limit]
    }
    return [(index, chunk) for index, chunk in indexed if index in keep]


def _batch_chunks(
    indexed: list[tuple[int, RetrievedChunk]], max_chars: int
) -> list[list[tuple[int, RetrievedChunk]]]:
    """Greedily pack chunks into batches of at most ``max_chars`` characters."""
    batches: list[list[tuple[int, RetrievedChunk]]] = []
    current: list[tuple[int, RetrievedChunk]] = []
    size = 0
    for index, chunk in indexed:
        cost = min(len(chunk.content), _EXCERPT_CHARS) + 32  # label + separators
        if current and size + cost > max_chars:
            batches.append(current)
            current, size = [], 0
        current.append((index, chunk))
        size += cost
    if current:
        batches.append(current)
    return batches


def _evidence_prompt(
    state: ResearchState, batch: list[tuple[int, RetrievedChunk]]
) -> tuple[list[dict[str, str]], Any]:
    excerpts = [
        f"[{_source_label(index)}]\n{chunk.content[:_EXCERPT_CHARS]}"
        for index, chunk in batch
    ]
    user = (
        "Research question:\n"
        f"{state.original_query}\n\n"
        "Retrieved excerpts:\n"
        + "\n\n".join(excerpts)
    )
    prompt = get_system_prompt(
        "research-evidence-extractor",
        fallback=prompts.EVIDENCE_SYSTEM,
    )
    messages = [
        {"role": "system", "content": prompt.text},
        {"role": "user", "content": user},
    ]
    return messages, prompt


def _claims_from_text(text: str) -> list[dict]:
    payload = parse_json_object(text)
    claims = payload.get("claims", [])
    return claims if isinstance(claims, list) else []


def _analyze_batch(
    state: ResearchState,
    services: ResearchServices,
    batch: list[tuple[int, RetrievedChunk]],
) -> list[EvidenceItem]:
    """Extract source-backed claims for one batch of chunks."""
    try:
        messages, prompt = _evidence_prompt(state, batch)
        with prompt_scope(prompt):
            text = services.llm(messages)
        claims = _claims_from_text(text)
    except Exception:
        logger.warning(
            "Evidence analysis failed for a batch of %d chunk(s); "
            "those chunks contribute no claims.",
            len(batch),
            exc_info=True,
        )
        return []

    evidence: list[EvidenceItem] = []
    for entry in claims:
        if not isinstance(entry, dict):
            continue
        try:
            index = int(entry.get("source_key"))
            chunk = state.retrieved[index]
        except (TypeError, ValueError, IndexError):
            continue
        claim_text = str(entry.get("claim", "")).strip()
        if not claim_text:
            continue
        confidence = float(entry.get("confidence", 0.5))
        evidence.append(
            _evidence_from_chunk(chunk, claim_text, max(0.0, min(1.0, confidence)))
        )
    return evidence


def evidence_analyzer_node(
    state: ResearchState, services: ResearchServices
) -> ResearchState:
    """Extract source-supported claims from the retrieved chunks."""
    state.status = "analyzing"
    if not state.retrieved:
        state.evidence = []
        return state

    indexed = _select_chunks(list(enumerate(state.retrieved)))
    batches = _batch_chunks(indexed, max(1, int(settings.evidence_batch_chars)))
    workers = max(1, int(settings.evidence_concurrency))

    # One batch (the common case) runs inline: no thread pool, no bookkeeping.
    if len(batches) == 1 or workers == 1:
        evidence = [
            item
            for batch in batches
            for item in _analyze_batch(state, services, batch)
        ]
    else:
        evidence = []
        with ThreadPoolExecutor(
            max_workers=min(workers, len(batches)), thread_name_prefix="evidence"
        ) as pool:
            # ``map`` preserves batch order, so the merged evidence list is
            # deterministic regardless of which model call finishes first.
            results = pool.map(
                lambda batch: _analyze_batch(state, services, batch), batches
            )
            for items in results:
                evidence.extend(items)

    # If the model gave no usable, source-backed claims, fall back to
    # deterministic grounding on real chunks (never model-generated claims).
    state.evidence = evidence or _fallback_evidence(state)
    return state
