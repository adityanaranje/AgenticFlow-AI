"""Document text extraction & normalization (Phase 4, §7).

Supported types: PDF, TXT, Markdown, DOCX.

Every parser returns a :class:`ParsedDocument` made of :class:`ParsedPage`
objects so downstream stages (chunking → citations) can preserve
page/section provenance where the format supports it:

    - PDF   -> one ParsedPage per page (``page_number`` = 1-based)
    - DOCX  -> one ParsedPage of body paragraphs
    - TXT   -> one ParsedPage
    - MD    -> one ParsedPage (markdown source kept as-is)

Text is *normalized* (consistent line endings, whitespace collapsed) by this
module before chunking.

The parser never inspects file bytes beyond extracting text; filenames and
MIME types are validated by the caller (see
:mod:`app.services.document_service`).
"""

from __future__ import annotations

import io
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from app.core.exceptions import ValidationError

# Canonical (extension -> parser) mapping.
SUPPORTED_EXTENSIONS = {"pdf", "txt", "md", "markdown", "docx"}

# extension -> primary MIME (used only as a hint / for validation). The API
# decides acceptance on extension + reported MIME both.
EXTENSION_MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MIME_TO_EXTENSION: dict[str, str] = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/x-markdown": "md",
    "application/markdown": "md",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

# Accepted MIME types for upload validation.
SUPPORTED_MIME_TYPES = set(MIME_TO_EXTENSION)


@dataclass
class ParsedPage:
    """One page / section of extracted text."""

    text: str
    page_number: Optional[int] = None  # 1-based; None when not page-oriented
    section: Optional[str] = None


@dataclass
class ParsedDocument:
    """Normalized text + structural provenance from one source file."""

    filename: str
    file_type: str  # canonical: pdf | txt | md | docx
    pages: list[ParsedPage] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text)

    @property
    def page_count(self) -> Optional[int]:
        """Number of extracted pages (None only when nothing was parsed).

        PDFs report their real page count (from the 1-based page numbers).
        Formats without page boundaries — TXT / MD / DOCX — are parsed as a
        single page and report 1, so the UI never shows a null page count
        for a successfully processed document.
        """
        if not self.pages:
            return None
        numbered = [p for p in self.pages if p.page_number is not None]
        if numbered:
            return len(numbered)
        return len(self.pages)


def normalize_text(raw: str) -> str:
    """Normalize extracted text: NFC, consistent newlines, tidy whitespace."""
    if raw is None:
        return ""
    text = unicodedata.normalize("NFC", raw)
    # Unify CRLF / CR to LF.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove trailing whitespace on each line.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # Collapse 3+ blank lines to a single blank line.
    lines: list[str] = []
    blank = 0
    for line in text.split("\n"):
        if not line.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        lines.append(line)
    return "\n".join(lines).strip()


def extension_of(filename: str) -> str:
    """Return a canonical supported extension from a filename ('' if none)."""
    if not filename:
        return ""
    name = filename.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    if dot <= 0 or dot == len(name) - 1:
        return ""
    ext = name[dot + 1 :].strip().lower()
    # Treat markdown and md as the canonical 'md'.
    if ext == "markdown":
        ext = "md"
    return ext if ext in SUPPORTED_EXTENSIONS else ""


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def parse_pdf(data: bytes) -> ParsedDocument:
    """Extract text per page from a PDF using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages: list[ParsedPage] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            # A corrupt page shouldn't kill the whole document.
            text = ""
        text = normalize_text(text)
        pages.append(ParsedPage(text=text, page_number=index))

    return ParsedDocument(
        filename="", file_type="pdf", pages=[p for p in pages if p.text]
    )


def parse_docx(data: bytes) -> ParsedDocument:
    """Extract text from a DOCX using python-docx.

    All non-empty paragraphs (headings and body) are preserved in document
    order so no content is lost. Heading text is kept inline; the most recent
    heading is also recorded as ``section`` provenance on the returned page.
    """
    from docx import Document

    document = Document(io.BytesIO(data))
    parts: list[str] = []
    current_section: Optional[str] = None

    for paragraph in document.paragraphs:
        text = (paragraph.text or "").strip()
        if not text:
            continue
        style_name = (paragraph.style.name or "").lower() if paragraph.style else ""
        if any(token in style_name for token in ("heading", "title")):
            current_section = text
        parts.append(text)

    body = normalize_text("\n".join(parts))
    page = ParsedPage(text=body, page_number=None, section=current_section)
    return ParsedDocument(filename="", file_type="docx", pages=[page] if body else [])


def parse_text(data: bytes, file_type: str) -> ParsedDocument:
    """Parse TXT / Markdown as plain normalized text."""
    text = normalize_text(_decode_text(data))
    page = ParsedPage(text=text, page_number=None)
    return ParsedDocument(
        filename="", file_type=file_type, pages=[page] if text else []
    )


def parse_document(
    data: bytes, *, file_type: str, filename: str = ""
) -> ParsedDocument:
    """Dispatch to the correct parser for a canonical ``file_type``."""
    key = (file_type or "").lower()
    if key == "markdown":
        key = "md"
    if key == "pdf":
        parsed = parse_pdf(data)
    elif key == "docx":
        parsed = parse_docx(data)
    elif key in ("txt", "md"):
        parsed = parse_text(data, key)
    else:
        raise ValidationError(f"Unsupported document type: {file_type!r}")

    parsed.filename = filename
    parsed.file_type = key
    return parsed


def is_supported_extension(filename: str) -> bool:
    """True when the filename ends in a supported extension."""
    return extension_of(filename) != ""
