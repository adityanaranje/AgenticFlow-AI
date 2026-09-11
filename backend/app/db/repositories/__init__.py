"""Supabase-backed repositories.

All row lookups use ``.limit(1)`` + :func:`first_row` instead of the removed
``.single()`` / ``.maybe_single()`` builders so the code works across
supabase-py / postgrest-py versions (they were dropped from the
insert/update builders in postgrest-py 2.10+).
"""

from __future__ import annotations

from typing import Any


def first_row(data: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Return the first row of a PostgREST response payload, or ``None``.

    Response ``.data`` is always a list; callers that expect at most one row
    should combine this with ``.limit(1)`` on the query builder.
    """

    return data[0] if data else None
