"""Tests for report storage (Phase 5, §12)."""

from app.agents.state import Citation, ResearchState, RetrievedChunk
from app.services import report_service


class FakeReportRepo:
    def __init__(self):
        self.reports = []
        self.sources = []

    def create(self, **kwargs):
        row = {"id": "report-1", **kwargs}
        self.reports.append(row)
        return row

    def create_source(self, data):
        row = dict(data)
        row.setdefault("id", "src-" + str(len(self.sources)))
        self.sources.append(row)
        return row


def _state_with_citations():
    state = ResearchState(
        research_id="r1",
        organization_id="org-A",
        user_id="u1",
        original_query="What are migration risks?",
        final_report="# Executive Summary\n\nSummary.\n\n# Research Question\n\nWhat are migration risks?\n\nbody [E0]",
        confidence=0.7,
    )
    state.retrieved = [
        RetrievedChunk(
            document_id="doc-1",
            chunk_id="chunk-real",
            content="risk content",
            filename="policy.pdf",
            page_number=1,
            score=0.9,
        )
    ]
    state.sections = [
        type("S", (), {"heading": "Executive Summary", "body": "Summary."})(),
        type("S", (), {"heading": "Research Question", "body": "What are migration risks?"})(),
    ]
    state.citations = [
        Citation(document_id="doc-1", chunk_id="chunk-real", filename="policy.pdf", page_number=1, citation_label="E0"),
        Citation(document_id="doc-9", chunk_id="fabricated", filename="other.pdf", citation_label="E9"),
    ]
    return state


def test_store_report_persists_only_grounded_sources(monkeypatch):
    repo = FakeReportRepo()
    monkeypatch.setattr(report_service, "ReportRepository", lambda: repo)

    state = _state_with_citations()
    report = report_service.store_report(state)

    assert report is not None
    assert report["id"] == "report-1"
    # fabricated citation dropped
    assert len(repo.sources) == 1
    stored = repo.sources[0]
    assert stored["chunk_id"] == "chunk-real"
    assert "policy.pdf" in stored["citation"]


def test_store_report_sections_present(monkeypatch):
    repo = FakeReportRepo()
    monkeypatch.setattr(report_service, "ReportRepository", lambda: repo)
    state = _state_with_citations()
    report_service.store_report(state)
    sections = repo.reports[0]["sections"]
    assert "Executive Summary" in sections
    assert "Research Question" in sections
