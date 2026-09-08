"""Evidence analyzer node (Phase 5, §5/§8)."""

from __future__ import annotations

from app.agents import prompts
from app.agents.context import ResearchServices
from app.agents.llm import parse_json_object
from app.agents.state import EvidenceItem, ResearchState, RetrievedChunk


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


def evidence_analyzer_node(
    state: ResearchState, services: ResearchServices
) -> ResearchState:
    """Extract source-supported claims from the retrieved chunks."""
    state.status = "analyzing"
    if not state.retrieved:
        state.evidence = []
        return state

    excerpts = []
    for i, chunk in enumerate(state.retrieved):
        excerpts.append(f"[{_source_label(i)}]\n{chunk.content[:3000]}")

    system = prompts.EVIDENCE_SYSTEM
    user = (
        "Research question:\n"
        f"{state.original_query}\n\n"
        "Retrieved excerpts:\n"
        + "\n\n".join(excerpts)
    )

    text = services.llm(
        [{"role": "system", "content": system}, {"role": "user", "content": user}]
    )

    evidence: list[EvidenceItem] = []
    try:
        payload = parse_json_object(text)
        claims = payload.get("claims", [])
        for entry in claims:
            try:
                idx = int(entry.get("source_key"))
                chunk = state.retrieved[idx]
            except (TypeError, ValueError, IndexError):
                continue
            claim_text = str(entry.get("claim", "")).strip()
            if not claim_text:
                continue
            confidence = float(entry.get("confidence", 0.5))
            evidence.append(
                _evidence_from_chunk(chunk, claim_text, max(0.0, min(1.0, confidence)))
            )
    except Exception:
        evidence = []

    # If the model gave no usable, source-backed claims, fall back to
    # deterministic grounding on real chunks (never model-generated claims).
    state.evidence = evidence or _fallback_evidence(state)
    return state
