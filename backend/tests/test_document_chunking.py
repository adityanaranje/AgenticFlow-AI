"""Tests for recursive chunking (Phase 4, §8)."""

from app.services.chunking import chunk_text
from app.services.document_parser import ParsedDocument, ParsedPage


def test_chunk_monotonic_unique_indices(sample_txt):
    chunks = chunk_text(sample_txt, chunk_size=800, chunk_overlap=100)
    assert len(chunks) > 1
    indices = [c.chunk_index for c in chunks]
    assert indices == sorted(indices)
    assert len(set(indices)) == len(indices)


def test_chunk_content_nonempty_and_bounded(sample_txt):
    chunks = chunk_text(sample_txt, chunk_size=800, chunk_overlap=100)
    for chunk in chunks:
        assert chunk.content.strip()
        assert chunk.char_count >= 1
        # chunks shouldn't be wildly oversized
        assert chunk.char_count <= 800 + 100


def test_chunk_metadata_and_estimate(sample_txt):
    chunks = chunk_text(
        sample_txt, chunk_size=800, chunk_overlap=100, extra_metadata={"filename": "x.txt"}
    )
    assert chunks[0].metadata.get("filename") == "x.txt"
    assert chunks[0].token_estimate >= 1


def test_pages_provenance_preserved():
    # Long multi-paragraph content per page so chunking spans both pages.
    page_a_text = "\n\n".join(f"Alpha paragraph {i} on page one." for i in range(40))
    page_b_text = "\n\n".join(f"Beta paragraph {i} on page two." for i in range(40))
    page_a = ParsedPage(text=page_a_text, page_number=1)
    page_b = ParsedPage(text=page_b_text, page_number=2)
    doc = ParsedDocument(filename="multi.pdf", file_type="pdf", pages=[page_a, page_b])
    from app.services.chunking import chunk_pages

    chunks = chunk_pages(doc.pages, chunk_size=120, chunk_overlap=20)
    assert len(chunks) > 2
    page_numbers = [c.page_number for c in chunks]
    # The first chunk must originate on page one, and page-two chunks exist
    # after page-one chunks (provenance follows the source pages in order).
    assert page_numbers[0] == 1
    assert 2 in page_numbers
    first_page_two = page_numbers.index(2)
    assert all(n in (1, 2) for n in page_numbers[: first_page_two + 1])
    # The last chunk belongs to page two and contains its content.
    assert chunks[-1].page_number == 2
    assert "Beta" in chunks[-1].content


def test_small_document_single_chunk():
    chunks = chunk_text("Short doc.", chunk_size=1500, chunk_overlap=200)
    assert len(chunks) == 1
    assert chunks[0].content == "Short doc."


def test_empty_returns_no_chunks():
    assert chunk_text("   \n\n  ") == []
