"""Text sanitization helpers (Postgres-safe strings).

PostgreSQL text/varchar/jsonb columns reject NUL bytes: any value containing
one fails the insert with error 22P05 ("unsupported Unicode escape
sequence"). Extracted document text can legitimately contain NULs (PDF
ToUnicode maps, UTF-16 decodes, DOCX XML), so every ingestion write path
strips them before the row reaches PostgREST. NULs carry no linguistic
meaning, so dropping them is lossless for embeddings, retrieval and
citations.
"""

from __future__ import annotations

from typing import TypeVar

_T = TypeVar("_T")

# NUL (U+0000). Written as chr(0) so the source never contains a raw NUL
# byte or a backslash escape; PostgreSQL rejects this character in
# text/jsonb with error 22P05.
_NUL = chr(0)


def sanitize_text_for_postgres(text: str) -> str:
    """Remove characters PostgreSQL cannot store in text/jsonb.

    - NUL bytes: rejected with error 22P05. Dropped.
    - Lone surrogates (U+D800-U+DFFF): not valid UTF-8 or JSON.
      Dropped so the value survives JSON encoding + insertion.

    Every other character (including newlines, tabs and non-ASCII text) is
    preserved byte-for-byte. Non-string input is returned unchanged.
    """
    if not text or not isinstance(text, str):
        return text
    if _NUL in text:
        text = text.replace(_NUL, "")
        if not text:
            return text
    if text.isascii():
        return text
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        # Only lone surrogates are unencodable in UTF-8; drop them.
        text = text.encode("utf-8", "ignore").decode("utf-8", "ignore")
    return text


def sanitize_for_postgres(value: _T) -> _T:
    """Recursively strip Postgres-illegal characters from ``value``.

    Strings are cleaned with :func:`sanitize_text_for_postgres`; dicts,
    lists and tuples are rebuilt with cleaned keys/values/items; every
    other type is returned unchanged.
    """
    if isinstance(value, str):
        return sanitize_text_for_postgres(value)  # type: ignore[return-value]
    if isinstance(value, dict):
        return {  # type: ignore[return-value]
            sanitize_for_postgres(key): sanitize_for_postgres(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_for_postgres(item) for item in value]  # type: ignore[return-value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_postgres(item) for item in value)  # type: ignore[return-value]
    return value
