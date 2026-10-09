"""Regression tests: NUL bytes must never reach Postgres.

PostgreSQL rejects NUL in text/jsonb with 22P05 ("unsupported Unicode
escape sequence"). Extracted document text can contain NULs (PDF ToUnicode
maps, UTF-16 decodes), which used to crash chunk inserts in
``DocumentRepository.create_chunks`` and fail the whole document.
Every ingestion write path now strips them.
"""

import sys

NUL = chr(0)


def _contains_nul(value) -> bool:
    """Recursively check for NUL bytes in nested str/dict/list/tuple."""
    if isinstance(value, str):
        return NUL in value
    if isinstance(value, dict):
        return any(_contains_nul(k) or _contains_nul(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_nul(item) for item in value)
    return False


# ----------------------------------------------------------------------
# core.text unit tests
# ----------------------------------------------------------------------


def test_sanitize_text_strips_nul():
    from app.core.text import sanitize_text_for_postgres

    assert sanitize_text_for_postgres("a" + NUL + "b") == "ab"
    assert sanitize_text_for_postgres(NUL + NUL) == ""
    assert sanitize_text_for_postgres("") == ""
    assert sanitize_text_for_postgres("plain") == "plain"
    # Meaningful whitespace and non-ASCII text are preserved.
    assert sanitize_text_for_postgres("a\nb\t" + NUL + "caf" + chr(233)) == "a\nb\tcaf" + chr(233)
    # Non-string input passes through untouched.
    assert sanitize_text_for_postgres(None) is None
    assert sanitize_text_for_postgres(123) == 123


def test_sanitize_text_strips_lone_surrogates():
    from app.core.text import sanitize_text_for_postgres

    assert sanitize_text_for_postgres("a" + chr(0xD800) + "b") == "ab"


def test_sanitize_for_postgres_recursive():
    from app.core.text import sanitize_for_postgres

    dirty = {
        "content": "x" + NUL + "y",
        "nested": {"tags": ["a" + NUL, "b"], "count": 3},
        "pair": ("p" + NUL, None),
        "score": 1.5,
    }
    clean = sanitize_for_postgres(dirty)
    assert not _contains_nul(clean)
    assert clean["content"] == "xy"
    assert clean["nested"] == {"tags": ["a", "b"], "count": 3}
    assert clean["pair"] == ("p", None)
    assert clean["score"] == 1.5
    # The input is not mutated.
    assert _contains_nul(dirty)


# ----------------------------------------------------------------------
# parser + chunking
# ----------------------------------------------------------------------


def test_normalize_text_strips_nul():
    from app.services.document_parser import normalize_text

    assert normalize_text("hello" + NUL + "world") == "helloworld"
    assert normalize_text("a" + NUL + "\r\n\r\nb") == "a\n\nb"


def test_parse_text_bytes_with_nul():
    from app.services.document_parser import parse_document

    raw = ("AgentFlow keeps tenants separate." + NUL + "\n\nSecond paragraph.\n").encode("utf-8")
    parsed = parse_document(raw, file_type="txt", filename="a.txt")
    assert not _contains_nul(parsed.full_text)
    assert "tenants separate" in parsed.full_text


def test_chunk_pages_strips_nul_from_raw_text_and_metadata():
    from app.services import chunking
    from app.services.document_parser import ParsedPage

    pages = [
        ParsedPage(
            text=("Tenant isolation" + NUL + " keeps orgs separate.\n\nSecond paragraph here.\n"),
            page_number=1,
        )
    ]
    chunks = chunking.chunk_pages(
        pages,
        chunk_size=500,
        chunk_overlap=50,
        extra_metadata={"filename": "re" + NUL + "port.txt"},
    )
    assert chunks
    for chunk in chunks:
        assert not _contains_nul(chunk.content)
        assert not _contains_nul(chunk.metadata)
    assert chunks[0].metadata["filename"] == "report.txt"


# ----------------------------------------------------------------------
# worker builders + pipeline
# ----------------------------------------------------------------------


def test_chunk_row_and_point_strip_nul():
    from app.services.chunking import TextChunk
    from app.workers import document_worker

    chunk = TextChunk(
        chunk_index=0,
        content="body" + NUL + "text",
        page_number=2,
        metadata={"filename": "f" + NUL + ".txt"},
    )
    row = document_worker._chunk_row(
        document_id="doc-1",
        organization_id="org-1",
        chunk_id="chunk-1",
        chunk=chunk,
    )
    assert not _contains_nul(row)
    assert row["content"] == "bodytext"

    point = document_worker._chunk_point(
        chunk=chunk,
        vector=[0.1, 0.2],
        chunk_id="chunk-1",
        document_id="doc-1",
        organization_id="org-1",
        filename="f" + NUL + ".txt",
        file_type="txt",
    )
    assert not _contains_nul(point["payload"])
    assert point["payload"]["content"] == "bodytext"


class _BulkRepo:
    """Fake repository with the bulk insert path (mirrors the traceback)."""

    def __init__(self, record):
        self.record = dict(record)
        self.updates = []
        self.inserted_rows = []

    def get_document(self, document_id):
        if document_id == self.record["id"]:
            return dict(self.record)
        return None

    def update(self, document_id, organization_id, fields):
        self.updates.append((document_id, organization_id, dict(fields)))
        self.record.update(fields)
        return dict(self.record)

    def delete_chunks(self, document_id, organization_id):
        pass

    def create_chunks(self, rows):
        # Simulate Postgres: reject any NUL like error 22P05 does.
        for row in rows:
            if _contains_nul(row):
                raise ValueError("unsupported Unicode escape sequence (22P05)")
        self.inserted_rows.extend(dict(r) for r in rows)
        return [{"id": r["id"]} for r in rows]


class _FakeVectorStore:
    def __init__(self):
        self.upserts = []

    def ensure_collection(self, client=None):
        pass

    def delete_document_vectors(self, organization_id, document_id):
        pass

    def upsert_chunk_vectors(self, points, client=None, **kwargs):
        for point in points:
            if _contains_nul(point["payload"]):
                raise ValueError("NUL leaked into vector payload")
        self.upserts.append(points)


def test_process_document_with_nul_content_completes(monkeypatch):
    from app.services.document_parser import ParsedDocument, ParsedPage
    from app.workers import document_worker

    doc = {
        "id": "doc-nul",
        "organization_id": "org-A",
        "filename": "re" + NUL + "port.txt",
        "file_type": "txt",
        "status": "pending",
    }
    repo = _BulkRepo(doc)
    store = _FakeVectorStore()
    embedded = {}

    parsed = ParsedDocument(
        filename="report.txt",
        file_type="txt",
        pages=[
            ParsedPage(
                text=(
                    "Tenant isolation" + NUL + " keeps organizations separate.\n\n"
                    "Security boundaries are enforced per tenant.\n\n"
                    "Document processing extracts text then embeds chunks.\n"
                )
                * 10,
                page_number=None,
            )
        ],
    )

    monkeypatch.setattr(document_worker, "DocumentRepository", lambda: repo)
    monkeypatch.setattr(
        document_worker.document_storage, "download_document", lambda o, d, f: b"bytes"
    )
    monkeypatch.setattr(
        document_worker.document_parser,
        "parse_document",
        lambda d, file_type=None, filename="": parsed,
    )

    def _fake_embed(texts):
        embedded["texts"] = list(texts)
        return [[0.1] * 3 for _ in texts]

    monkeypatch.setattr(document_worker.embeddings, "embed_texts_batched", _fake_embed)
    monkeypatch.setattr(document_worker.vector_store, "ensure_collection", store.ensure_collection)
    monkeypatch.setattr(
        document_worker.vector_store, "delete_document_vectors", store.delete_document_vectors
    )
    monkeypatch.setattr(
        document_worker.vector_store, "upsert_chunk_vectors", store.upsert_chunk_vectors
    )

    result = document_worker.process_document("doc-nul")

    assert result["status"] == "completed"
    assert repo.inserted_rows, "chunks must be persisted to DB"
    assert not _contains_nul(repo.inserted_rows)
    assert not _contains_nul(embedded["texts"])
    assert store.upserts and len(store.upserts[0]) == len(repo.inserted_rows)


# ----------------------------------------------------------------------
# repositories (PostgREST boundary)
# ----------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeBuilder:
    def __init__(self, table):
        self._table = table
        self._op = "select"
        self._rows = None
        self._filters = {}

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

    def select(self, *columns, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def limit(self, n):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._op == "insert":
            for row in self._rows:
                if _contains_nul(row):
                    raise ValueError("unsupported Unicode escape sequence (22P05)")
            self._table["rows"].extend(dict(r) for r in self._rows)
            return _FakeResponse(list(self._rows))
        if self._op == "update":
            if _contains_nul(self._rows):
                raise ValueError("unsupported Unicode escape sequence (22P05)")
            return _FakeResponse([dict(self._rows)])
        return _FakeResponse([])


class _FakeClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return _FakeBuilder(self.tables.setdefault(name, {"rows": []}))


def _patch_supabase(monkeypatch, module_path):
    client = _FakeClient()
    module = sys.modules.get(module_path)
    if module is None:
        __import__(module_path)
        module = sys.modules[module_path]
    monkeypatch.setattr(module, "get_supabase", lambda: client)
    return client


def test_document_repository_create_chunks_strips_nul(monkeypatch):
    from app.db.repositories.documents import DocumentRepository

    client = _patch_supabase(monkeypatch, "app.db.repositories.documents")
    repo = DocumentRepository()

    rows = [
        {
            "id": "chunk-1",
            "document_id": "doc-1",
            "organization_id": "org-1",
            "chunk_index": 0,
            "content": "hello" + NUL + "world",
            "metadata": {"filename": "a" + NUL + ".txt"},
            "vector_point_id": "chunk-1",
        }
    ]
    inserted = repo.create_chunks(rows)
    assert len(inserted) == 1
    stored = client.tables["document_chunks"]["rows"][0]
    assert stored["content"] == "helloworld"
    assert stored["metadata"] == {"filename": "a.txt"}

    single = repo.create_chunk(
        {
            "document_id": "doc-1",
            "organization_id": "org-1",
            "chunk_index": 1,
            "content": "x" + NUL,
        }
    )
    assert single["content"] == "x"


def test_report_and_research_repositories_strip_nul(monkeypatch):
    from app.db.repositories.reports import ReportRepository
    from app.db.repositories.research import ResearchRepository

    reports_client = _patch_supabase(monkeypatch, "app.db.repositories.reports")
    research_client = _patch_supabase(monkeypatch, "app.db.repositories.research")

    report = ReportRepository().create(
        research_run_id="run-1",
        organization_id="org-1",
        title="ti" + NUL + "tle",
        content="bo" + NUL + "dy",
    )
    assert report["title"] == "title"
    assert reports_client.tables["reports"]["rows"][0]["content"] == "body"

    ReportRepository().create_source(
        {
            "report_id": report["id"],
            "organization_id": "org-1",
            "quote": "q" + NUL + "uote",
        }
    )
    assert reports_client.tables["report_sources"]["rows"][0]["quote"] == "quote"

    run = ResearchRepository().create(
        organization_id="org-1",
        user_id="user-1",
        question="wh" + NUL + "at?",
    )
    assert run["question"] == "what?"
    assert research_client.tables["research_runs"]["rows"][0]["question"] == "what?"


# ----------------------------------------------------------------------
# embeddings input
# ----------------------------------------------------------------------


def test_embed_texts_strips_nul_before_provider_call(monkeypatch):
    from app.services import embeddings

    class _Item:
        def __init__(self, index):
            self.index = index
            self.embedding = [0.1, 0.2]

    class _EmbeddingsAPI:
        def __init__(self):
            self.last_input = None

        def create(self, model, input):
            self.last_input = input
            assert not _contains_nul(input)

            class _Resp:
                pass

            resp = _Resp()
            resp.data = [_Item(i) for i in range(len(input))]
            return resp

    api = _EmbeddingsAPI()

    class _Client:
        embeddings = api

    monkeypatch.setattr(embeddings, "get_openai_client", lambda: _Client())
    vectors = embeddings.embed_texts(["a" + NUL + "b", "clean"])
    assert len(vectors) == 2
    assert api.last_input == ["ab", "clean"]
