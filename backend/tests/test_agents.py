"""Agent node + full pipeline tests (Phase 5, §5/§6/§7/§8/§9/§10/§11)."""

import json

from app.agents.context import ResearchServices
from app.agents.nodes.citation_validator import citation_validator_node, extract_citations
from app.agents.nodes.evidence_analyzer import evidence_analyzer_node
from app.agents.nodes.finalizer import finalizer_node
from app.agents.nodes.gap_detector import gap_detector_node
from app.agents.nodes.planner import planner_node
from app.agents.nodes.retriever import retriever_node
from app.agents.nodes.synthesis import synthesis_node
from app.agents.state import ResearchState, RetrievedChunk


def _fake_llm(messages):
    system = (messages[0].get("content") or "").lower()
    if "research planner" in system:
        return json.dumps(
            {"sub_questions": ["Security risks", "Cost risks", "Compliance risks"]}
        )
    if "retrieved document excerpts" in system or "important, source-supported" in system:
        return json.dumps(
            {"claims": [{"claim": "Cloud migration poses security risks.", "source_key": 0, "confidence": 0.8}]}
        )
    if "sufficient" in system and "follow_up" in system:
        return json.dumps({"sufficient": True, "gaps": [], "follow_up_queries": []})
    if "grounded research report" in system:
        return (
            "# Executive Summary\n\nThere is evidence of security risk. [E0]\n"
            "# Research Question\n\nWhat are migration risks?\n"
            "# Key Findings\n\nFound a risk. [E0]\n"
            "# Detailed Analysis\n\nAnalysis. [E0]\n"
            "# Evidence\n\n- security risk [E0]\n"
            "# Risks / Limitations\n\nLimited sources.\n"
            "# Conclusion\n\nConclude.\n"
            "# Sources\n\n[E0] company_policy.pdf p.1\n"
        )
    raise AssertionError(f"unhandled llm prompt: {system[:60]}")


def _fake_chunk(doc="doc-1", chunk="chunk-1", page=1):
    return RetrievedChunk(
        document_id=doc,
        chunk_id=chunk,
        content="Cloud migration poses security, cost and compliance risks for the firm.",
        filename="company_policy.pdf",
        page_number=page,
        chunk_index=3,
        score=0.87,
    )


def _services(retrieve):
    s = ResearchServices(llm=_fake_llm, retrieve=retrieve, config={"max_subquestions": 5, "max_iterations": 3, "top_k": 5})
    return s


def _state():
    return ResearchState(
        research_id="r1",
        organization_id="org-A",
        user_id="u1",
        original_query="What are the risks in our cloud migration?",
        config={"max_subquestions": 5, "max_iterations": 3, "top_k": 5},
    )


def test_planner_bounds_subquestions():
    seen_org = {}

    def retrieve(org, query, top_k, filters=None):
        seen_org[org] = True
        return [_fake_chunk()]

    state = _state()
    state = planner_node(state, _services(retrieve))
    assert len(state.sub_questions) <= 5
    assert "Security risks" in state.sub_questions
    assert state.original_query in state.search_queries


def test_retriever_scopes_to_org_and_dedupes():
    calls = []
    seen_org = {}

    def retrieve(org, query, top_k, filters=None):
        calls.append(query)
        seen_org[org] = True
        return [_fake_chunk(), _fake_chunk()]  # duplicate chunk

    state = _state()
    state.sub_questions = ["A", "B"]
    state.search_queries = ["A", "B"]
    state = retriever_node(state, _services(retrieve))
    assert seen_org.get("org-A") is True
    # dedupe keeps 1
    assert len(state.retrieved) == 1
    assert all(c.chunk_id == "chunk-1" for c in state.retrieved)


def test_evidence_is_grounded_to_real_chunk():
    def retrieve(org, query, top_k, filters=None):
        return [_fake_chunk()]

    state = _state()
    state.retrieved = [_fake_chunk()]
    state = evidence_analyzer_node(state, _services(retrieve))
    assert state.evidence, "must produce evidence"
    ev = state.evidence[0]
    assert ev.document_id == "doc-1"
    assert ev.chunk_id == "chunk-1"
    assert "security" in ev.claim.lower() or "cloud" in ev.claim.lower()


def test_evidence_fallback_uses_real_chunks_when_llm_bad():
    def llm_bad(messages):
        raise AssertionError("llm should not be used on empty retrieval")

    def retrieve(org, query, top_k, filters=None):
        return []

    state = _state()
    state.retrieved = [_fake_chunk()]
    s = ResearchServices(llm=lambda m: "not json", retrieve=retrieve, config={})
    state = evidence_analyzer_node(state, s)
    # fallback: claim derived from chunk text, never fabricated
    assert state.evidence
    assert state.evidence[0].chunk_id == "chunk-1"


def test_full_pipeline_grounded_citations_and_report():
    def retrieve(org, query, top_k, filters=None):
        return [_fake_chunk()]

    services = _services(retrieve)
    state = _state()
    state = planner_node(state, services)

    iteration = 0
    while iteration <= int(state.config["max_iterations"]):
        state = retriever_node(state, services)
        state = evidence_analyzer_node(state, services)
        state = gap_detector_node(state, services)
        if state.search_queries and iteration < state.config["max_iterations"]:
            iteration += 1
            continue
        break

    state = synthesis_node(state, services)
    state = citation_validator_node(state, services)
    state = finalizer_node(state, services)

    assert state.status == "completed"
    assert state.final_report and "Executive Summary" in state.final_report
    assert state.citations, "valid citations must exist"
    # every citation maps to a retrieved chunk (grounded)
    for c in state.citations:
        assert any(r.chunk_id == c.chunk_id for r in state.retrieved)
    assert state.confidence is not None and 0 <= state.confidence <= 1
    assert extract_citations(state.final_report)


def test_citation_validator_drops_fabricated():
    def retrieve(org, query, top_k, filters=None):
        return []

    from app.agents.state import EvidenceItem

    state = _state()
    state.retrieved = [_fake_chunk()]
    state.evidence = [
        EvidenceItem(
            claim="risk",
            supporting_source="company_policy.pdf",
            document_id="doc-1",
            chunk_id="chunk-1",
            supporting_chunk="x",
            confidence=0.8,
            filename="company_policy.pdf",
            page_number=1,
        )
    ]
    # draft cites E0 (valid) and E99 (fabricated)
    state.draft = "Risk statement [E0] and a bogus one [E99]."
    state = citation_validator_node(state, _services(retrieve))
    assert len(state.citations) == 1
    assert state.citations[0].citation_label == "E0"
    assert any("fabricated" in e for e in state.errors)
