"""Tests for citations + evaluation + report storage (Phase 5, §11/§12/§20)."""

import pytest

from app.agents.state import Citation, RetrievedChunk
from app.services import citations
from app.services.evaluation_service import evaluate_report_content


def _chunk(cid):
    return RetrievedChunk(
        document_id="doc-1",
        chunk_id=cid,
        content="c",
        filename="policy.pdf",
        page_number=12,
        chunk_index=1,
        score=0.9,
    )


def test_format_citation_no_fabrication():
    assert citations.format_citation("company_policy.pdf", 12) == "[company_policy.pdf, p.12]"
    assert citations.format_citation("a.txt", chunk=3) == "[a.txt, chunk 3]"
    assert citations.format_citation("x.pdf") == "[x.pdf]"


def test_filter_grounded_citations_rejects_fabricated():
    available = [_chunk("chunk-1")]
    grounded = [
        Citation(document_id="doc-1", chunk_id="chunk-1", filename="policy.pdf", citation_label="E0"),
    ]
    fabricated = [
        Citation(document_id="doc-9", chunk_id="never-retrieved", filename="other.pdf", citation_label="E7"),
    ]
    kept, dropped = citations.filter_grounded_citations(grounded + fabricated, available)
    assert len(kept) == 1 and kept[0].chunk_id == "chunk-1"
    assert len(dropped) == 1 and dropped[0].chunk_id == "never-retrieved"


def test_evaluate_report_content_metrics():
    content = (
        "# Report\n\nThere is risk to migrations. [E0]\n\n"
        "Another finding. [E1]\n\nFabricated ref [E9] should be ignored for grounding count."
    )
    sources = [
        {"metadata": {"citation_label": "E0", "retrieval_score": 0.9}},
        {"metadata": {"citation_label": "E1", "retrieval_score": 0.8}},
    ]
    result = evaluate_report_content(content, sources)
    m = result["metrics"]
    # E9 not grounded => correctness < 1
    assert 0 < m["citation_correctness"] < 1
    assert m["citation_completeness"] == 1.0  # E0,E1 both stored & cited
    assert 0 < m["groundedness"] <= 1
    assert m["relevance"] == pytest.approx((0.9 + 0.8) / 2)
    assert 0 <= m["answer_quality"] <= 1
    # raw explanations preserved for inspection
    assert "referenced_labels" in result["explanations"]
