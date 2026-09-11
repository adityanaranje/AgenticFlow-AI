"""Regression tests: repositories must work with postgrest-py 2.10+ clients.

Newer supabase/postgrest releases removed ``.single()`` / ``.maybe_single()``
from the query builders (and ``count``/``head`` kwargs from ``select()``), so
repositories must use plain ``.execute()`` on list responses plus first-row
extraction. These tests drive the repositories against a fake client that
mimics that newer API surface — calling removed methods would explode here.
"""

from app.db.repositories.documents import DocumentRepository


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeBuilder:
    """Chainable fake mirroring the postgrest-py 2.31 builder surface."""

    def __init__(self, table, op):
        self._table = table
        self._op = op
        self._rows = None
        self._filters = {}
        self._limit = None

    # -- operations -----------------------------------------------------
    def insert(self, rows):
        self._op = "insert"
        self._rows = rows if isinstance(rows, list) else [rows]
        return self

    def update(self, fields):
        self._op = "update"
        self._rows = fields
        return self

    def delete(self):
        self._op = "delete"
        return self

    # -- transforms -----------------------------------------------------
    def select(self, *columns, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def limit(self, n):
        self._limit = n
        return self

    def order(self, *_args, **_kwargs):
        return self

    # -- terminal --------------------------------------------------------
    def _matched(self):
        return [
            r for r in self._table["rows"] if all(r.get(k) == v for k, v in self._filters.items())
        ]

    def execute(self):
        if self._op == "insert":
            self._table["rows"].extend(dict(r) for r in self._rows)
            return FakeResponse(list(self._rows))
        matched = self._matched()
        if self._op == "update":
            for row in matched:
                row.update(self._rows)
            return FakeResponse(matched)
        if self._op == "delete":
            self._table["rows"][:] = [r for r in self._table["rows"] if r not in matched]
            return FakeResponse(matched)
        if self._limit is not None:
            matched = matched[: self._limit]
        return FakeResponse(matched)


class FakeClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return FakeBuilder(self.tables.setdefault(name, {"rows": []}), "select")


def _repo(monkeypatch):
    client = FakeClient()
    import app.db.repositories.documents as repo_mod

    monkeypatch.setattr(repo_mod, "get_supabase", lambda: client)
    return DocumentRepository(), client


def test_create_and_lookup_round_trip(monkeypatch):
    repo, _ = _repo(monkeypatch)

    created = repo.create(
        {
            "id": "doc-1",
            "organization_id": "org-1",
            "uploaded_by": "user-1",
            "filename": "a.txt",
            "storage_path": "organizations/org-1/documents/doc-1/a.txt",
            "file_type": "txt",
            "file_size": 5,
            "checksum": "abc123",
            "status": "pending",
        }
    )
    assert created and created["id"] == "doc-1"

    assert repo.get_by_id("doc-1", "org-1")["checksum"] == "abc123"
    assert repo.get_by_id("doc-1", "org-2") is None  # tenant scoping
    assert repo.get_document("doc-1")["organization_id"] == "org-1"
    assert repo.get_by_checksum("org-1", "abc123")["id"] == "doc-1"
    assert repo.get_by_checksum("org-1", "missing") is None
    assert repo.get_by_checksum("org-2", "abc123") is None


def test_update_and_delete(monkeypatch):
    repo, _ = _repo(monkeypatch)
    repo.create(
        {
            "id": "doc-2",
            "organization_id": "org-1",
            "checksum": "def456",
            "status": "processing",
        }
    )

    updated = repo.update("doc-2", "org-1", {"status": "completed", "metadata": {"chunk_count": 2}})
    assert updated["status"] == "completed"
    assert repo.get_by_id("doc-2", "org-1")["metadata"]["chunk_count"] == 2

    assert repo.delete("doc-2", "org-1") is True
    assert repo.get_document("doc-2") is None


def test_chunk_helpers(monkeypatch):
    repo, _ = _repo(monkeypatch)
    for i in range(3):
        chunk = repo.create_chunk(
            {
                "document_id": "doc-9",
                "organization_id": "org-1",
                "chunk_index": i,
                "content": f"chunk {i}",
            }
        )
        assert chunk["chunk_index"] == i

    assert repo.count_chunks("doc-9", "org-1") == 3
    assert len(repo.list_chunks("doc-9", "org-1")) == 3
    repo.delete_chunks("doc-9", "org-1")
    assert repo.count_chunks("doc-9", "org-1") == 0
