"""Tests for document validation & upload orchestration (Phase 4, §2-§5)."""

from app.core.exceptions import ValidationError
from app.services import document_service


def test_resolve_file_type_valid():
    assert document_service.resolve_file_type("a.pdf", "application/pdf") == "pdf"
    assert document_service.resolve_file_type("a.txt", "text/plain") == "txt"
    assert document_service.resolve_file_type("a.md", "text/markdown") == "md"
    assert document_service.resolve_file_type(
        "a.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ) == "docx"


def test_resolve_file_type_unsupported_extension():
    try:
        document_service.resolve_file_type("song.mp3", "audio/mpeg")
        raise AssertionError("expected rejection")
    except ValidationError:
        pass


def test_resolve_file_type_unsupported_mime():
    try:
        document_service.resolve_file_type("a.pdf", "application/x-msdownload")
        raise AssertionError("expected rejection")
    except ValidationError:
        pass


def test_resolve_file_type_mime_mismatch():
    # extension says pdf but MIME says docx -> rejected (never trust extension)
    try:
        document_service.resolve_file_type("a.pdf", "text/plain")
        raise AssertionError("expected rejection")
    except ValidationError:
        pass


def test_resolve_file_type_octet_stream_falls_back_to_extension():
    assert document_service.resolve_file_type("a.txt", "application/octet-stream") == "txt"


def test_size_rejections():
    # too large
    try:
        document_service.validate_file_size(999999999)
        raise AssertionError("expected rejection")
    except ValidationError:
        pass
    # empty
    try:
        document_service.validate_file_size(0)
        raise AssertionError("expected rejection")
    except ValidationError:
        pass


def test_checksum():
    assert document_service.compute_checksum(b"hello") == document_service.compute_checksum(
        b"hello"
    )
    assert document_service.compute_checksum(b"hello") != document_service.compute_checksum(
        b"hellp"
    )
    assert len(document_service.compute_checksum(b"x")) == 64  # sha256 hex


def test_storage_path_is_server_derived_and_scoped():
    from app.services import document_storage

    path = document_storage.build_storage_path("org-1", "doc-1", "annual report.pdf")
    assert path.startswith("organizations/org-1/documents/doc-1/")
    # path must never permit traversal or stray input
    assert "/../" not in path
    assert ".." not in path.split("/")[-1]
