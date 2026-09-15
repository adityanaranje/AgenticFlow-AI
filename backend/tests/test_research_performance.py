"""Throughput + robustness contracts for the research pipeline.

A research run is a chain of dependent model calls, so its latency is set by
how much independent work runs at once and how tight each provider call is.
These tests pin those properties down without asserting on wall-clock
durations (which would be flaky in CI):

    - every open query is retrieved with one embeddings request and
      concurrent vector searches, in a deterministic order;
    - retrieved chunks are analysed in batches that fit the model's context
      window, in parallel, with claims still mapped to the right chunk;
    - model calls are bounded by a timeout and retried only for transient
      errors;
    - progress writes stay small mid-run and cancellation checks read only
      the status column;
    - research workers execute several runs at once;
    - report sources are inserted in bulk.
"""

import json
import threading
import time

import pytest
from app.agents import llm as llm_mod
from app.agents import research_graph as graph_mod
from app.agents.context import ResearchServices
from app.agents.nodes.evidence_analyzer import evidence_analyzer_node
from app.agents.nodes.retriever import retriever_node
from app.agents.state import ResearchState, RetrievedChunk
from app.core.config import settings
from app.services import (
    background,
    document_service,
    embeddings,
    report_service,
    retrieval,
    vector_store,
)


def _chunk(index: int, score: float = 0.9, content: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=f"doc-{index}",
        chunk_id=f"chunk-{index}",
        content=content or f"Chunk {index} explains migration risk in detail.",
        filename=f"policy_{index}.pdf",
        page_number=1 + index,
        chunk_index=index,
        score=score,
    )


# --------------------------------------------------------------------------
# retrieval: one embeddings request, concurrent searches
# --------------------------------------------------------------------------
def test_retrieve_context_many_batches_embeddings_and_searches(monkeypatch):
    embed_calls: list[list[str]] = []
    search_calls: list[str] = []
    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_embed(texts):
        embed_calls.append(list(texts))
        return [[float(index)] for index in range(len(texts))]  # 0.0, 1.0, 2.0

    def fake_search(*, organization_id, query_vector, top_k=5, filters=None):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            search_calls.append(organization_id)
        time.sleep(0.05)
        with lock:
            active -= 1
        return [
            {
                "id": f"point-{query_vector[0]}",
                "score": 0.5,
                "payload": {
                    "document_id": "doc-1",
                    "document_chunk_id": f"chunk-{query_vector[0]}",
                    "content": "text",
                },
            }
        ]

    monkeypatch.setattr(retrieval.embeddings, "embed_texts", fake_embed)
    monkeypatch.setattr(retrieval.vector_store, "search_vectors", fake_search)

    results = retrieval.retrieve_context_many(
        organization_id="org-A",
        queries=["first query", "  ", "second query", "third query"],
        top_k=3,
        concurrency=3,
    )

    # ONE provider request carrying every non-blank query.
    assert len(embed_calls) == 1
    assert embed_calls[0] == ["first query", "second query", "third query"]
    # Order preserved, blank query short-circuited without a provider call.
    assert [len(batch) for batch in results] == [1, 0, 1, 1]
    assert results[0][0]["chunk_id"] == "chunk-0.0"
    assert results[2][0]["chunk_id"] == "chunk-1.0"
    assert results[3][0]["chunk_id"] == "chunk-2.0"
    assert search_calls == ["org-A", "org-A", "org-A"]
    assert max_active > 1, "vector searches were serialised"


def test_retrieve_context_many_single_query_skips_the_pool(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[0.25] for _ in texts])
    monkeypatch.setattr(retrieval.vector_store, "search_vectors", lambda **kwargs: [])
    assert retrieval.retrieve_context_many("org-A", ["only query"]) == [[]]


def test_retrieve_context_many_never_searches_another_tenant(monkeypatch):
    seen: list[str] = []

    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[0.1] for _ in texts])
    monkeypatch.setattr(
        retrieval.vector_store,
        "search_vectors",
        lambda **kwargs: seen.append(kwargs["organization_id"]) or [],
    )

    retrieval.retrieve_context_many("org-A", ["a", "b", "c"])
    assert seen == ["org-A", "org-A", "org-A"]


# --------------------------------------------------------------------------
# retriever node
# --------------------------------------------------------------------------
def test_retriever_uses_one_batch_call_for_all_pending_queries():
    calls: list[tuple[str, list[str]]] = []

    def retrieve_many(org, queries, top_k, filters=None):
        calls.append((org, list(queries)))
        return [[_chunk(index)] for index, _ in enumerate(queries)]

    services = ResearchServices(
        llm=lambda messages: "",
        retrieve=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("per-query retrieval must not be used when batching is available")
        ),
        config={"top_k": 5},
        retrieve_many=retrieve_many,
    )
    state = ResearchState(organization_id="org-A", search_queries=["q1", "q2", "q3"])

    state = retriever_node(state, services)

    assert len(calls) == 1
    assert calls[0] == ("org-A", ["q1", "q2", "q3"])
    assert [chunk.chunk_id for chunk in state.retrieved] == [
        "chunk-0",
        "chunk-1",
        "chunk-2",
    ]
    assert state.used_queries == ["q1", "q2", "q3"]
    assert state.gaps == []


def test_retriever_records_empty_results_and_dedupes():
    def retrieve_many(org, queries, top_k, filters=None):
        return [[], [_chunk(1), _chunk(1)], [_chunk(1)]]  # empty, duplicate, repeat

    services = ResearchServices(
        llm=lambda messages: "",
        retrieve=lambda *args, **kwargs: [],
        config={},
        retrieve_many=retrieve_many,
    )
    state = ResearchState(organization_id="org-A", search_queries=["q1", "q2", "q3"])

    state = retriever_node(state, services)

    assert [chunk.chunk_id for chunk in state.retrieved] == ["chunk-1"]
    assert state.gaps == ["q1"]  # only the query with no hits


def test_retriever_falls_back_to_per_query_when_the_batch_call_fails():
    per_query: list[str] = []

    def retrieve_many(org, queries, top_k, filters=None):
        raise RuntimeError("embeddings provider down")

    def retrieve(org, query, top_k, filters=None):
        per_query.append(query)
        if query == "bad":
            raise RuntimeError("search failed")
        return [_chunk(7)]

    services = ResearchServices(
        llm=lambda messages: "",
        retrieve=retrieve,
        config={},
        retrieve_many=retrieve_many,
    )
    state = ResearchState(organization_id="org-A", search_queries=["good", "bad", "also good"])

    state = retriever_node(state, services)

    # Every query was still attempted individually, so the failure of one
    # never costs the others their evidence.
    assert per_query == ["good", "bad", "also good"]
    assert [chunk.chunk_id for chunk in state.retrieved] == ["chunk-7"]  # deduped
    assert any("failed" in error for error in state.errors)
    assert state.gaps == []  # non-empty results are not gaps


def test_retriever_skips_queries_already_used():
    calls: list[list[str]] = []

    def retrieve_many(org, queries, top_k, filters=None):
        calls.append(list(queries))
        return [[] for _ in queries]

    services = ResearchServices(
        llm=lambda messages: "",
        retrieve=lambda *args, **kwargs: [],
        config={},
        retrieve_many=retrieve_many,
    )
    state = ResearchState(
        organization_id="org-A",
        search_queries=["q1", "q2", "q3"],
        used_queries=["q1"],
    )

    retriever_node(state, services)
    assert calls == [["q2", "q3"]]


# --------------------------------------------------------------------------
# evidence analyser
# --------------------------------------------------------------------------
def _claims_llm(state_counts: list[int], lock: threading.Lock, delay: float = 0.0):
    """Model double: one claim per source cited in the prompt."""

    def llm(messages):
        user = messages[-1]["content"]
        source_keys = []
        for line in user.splitlines():
            if line.startswith("[source:"):
                source_keys.append(int(line[len("[source:") : -1]))
        with lock:
            state_counts.append(len(source_keys))
        if delay:
            time.sleep(delay)
        return json.dumps(
            {
                "claims": [
                    {
                        "claim": f"Claim for source {key}",
                        "source_key": key,
                        "confidence": 0.7,
                    }
                    for key in source_keys
                ]
            }
        )

    return llm


def test_evidence_small_corpus_uses_a_single_call():
    """A typical run (a handful of chunks) costs one model call, as before."""
    calls: list[int] = []
    lock = threading.Lock()
    services = ResearchServices(llm=_claims_llm(calls, lock), retrieve=lambda *a, **k: [])

    state = ResearchState(organization_id="org-A", original_query="risks?")
    state.retrieved = [_chunk(index) for index in range(5)]

    state = evidence_analyzer_node(state, services)

    assert len(calls) == 1
    assert len(state.evidence) == 5
    assert [item.chunk_id for item in state.evidence] == [
        f"chunk-{index}" for index in range(5)
    ]


def test_evidence_large_corpus_is_batched_in_parallel(monkeypatch):
    """Chunks beyond one prompt are analysed in parallel batches, and every
    claim still maps to the chunk that supports it (global source indices)."""
    monkeypatch.setattr(settings, "evidence_batch_chars", 2000)
    monkeypatch.setattr(settings, "evidence_concurrency", 4)

    batch_sizes: list[int] = []
    lock = threading.Lock()
    active = 0
    max_active = 0

    def llm(messages):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            return _claims_llm(batch_sizes, lock, delay=0.05)(messages)
        finally:
            with lock:
                active -= 1

    services = ResearchServices(llm=llm, retrieve=lambda *a, **k: [])
    state = ResearchState(organization_id="org-A", original_query="risks?")
    state.retrieved = [_chunk(index, content="x" * 900) for index in range(8)]

    state = evidence_analyzer_node(state, services)

    assert len(batch_sizes) > 1, "the corpus should have been split into batches"
    assert max_active > 1, "batches were analysed sequentially"
    # Every claim survives with the right chunk and the right order.
    assert [item.chunk_id for item in state.evidence] == [
        f"chunk-{index}" for index in range(8)
    ]


def test_evidence_caps_the_corpus_by_retrieval_score(monkeypatch):
    monkeypatch.setattr(settings, "evidence_max_chunks", 3)
    monkeypatch.setattr(settings, "evidence_batch_chars", 100000)

    analysed: list[str] = []

    def llm(messages):
        analysed.extend(
            line.split("[source:")[1].rstrip("]")
            for line in messages[-1]["content"].splitlines()
            if line.startswith("[source:")
        )
        return json.dumps({"claims": []})

    services = ResearchServices(llm=llm, retrieve=lambda *a, **k: [])
    state = ResearchState(organization_id="org-A", original_query="risks?")
    # Scores 0.1 .. 0.9: the three highest-scoring chunks must be analysed.
    state.retrieved = [_chunk(index, score=0.1 * index) for index in range(9)]

    evidence_analyzer_node(state, services)

    assert len(analysed) == 3
    assert set(analysed) == {"6", "7", "8"}
    # Selection keeps retrieval order, so labels stay stable and sorted.
    assert analysed == ["6", "7", "8"]


def test_evidence_survives_a_failing_batch(monkeypatch):
    monkeypatch.setattr(settings, "evidence_batch_chars", 2000)
    monkeypatch.setattr(settings, "evidence_concurrency", 4)

    lock = threading.Lock()
    calls = {"n": 0}

    def llm(messages):
        with lock:
            calls["n"] += 1
            index = calls["n"]
        if index == 1:
            raise RuntimeError("prompt is too long")
        return json.dumps(
            {"claims": [{"claim": "ok", "source_key": 1, "confidence": 0.5}]}
        )

    services = ResearchServices(llm=llm, retrieve=lambda *a, **k: [])
    state = ResearchState(organization_id="org-A", original_query="risks?")
    state.retrieved = [_chunk(index, content="y" * 900) for index in range(4)]

    state = evidence_analyzer_node(state, services)

    # The failing batch contributes nothing; the other batches still do.
    assert state.evidence
    assert all(item.claim == "ok" for item in state.evidence)


def test_evidence_falls_back_when_every_batch_fails(monkeypatch):
    monkeypatch.setattr(settings, "evidence_batch_chars", 2000)

    def llm(messages):
        raise RuntimeError("model unavailable")

    services = ResearchServices(llm=llm, retrieve=lambda *a, **k: [])
    state = ResearchState(organization_id="org-A", original_query="risks?")
    state.retrieved = [_chunk(index, content="z" * 900) for index in range(4)]

    state = evidence_analyzer_node(state, services)

    # Deterministic grounding on real chunk text, never fabricated claims.
    assert state.evidence
    assert all(item.supporting_chunk for item in state.evidence)
    assert [item.chunk_id for item in state.evidence] == [
        f"chunk-{index}" for index in range(4)
    ]


# --------------------------------------------------------------------------
# model call bounds
# --------------------------------------------------------------------------
class _FakeCompletions:
    def __init__(self, failures_before_success: int, error: Exception):
        self.failures = failures_before_success
        self.error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failures > 0:
            self.failures -= 1
            raise self.error
        message = type("Message", (), {"content": "ok"})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self, completions):
        self.chat = type("Chat", (), {"completions": completions})()


class RateLimitError(Exception):
    """Named like the openai SDK error: transient, must be retried."""


class BadRequestError(Exception):
    """Permanent: must never be retried."""


def test_chat_bounds_the_request_timeout(monkeypatch):
    completions = _FakeCompletions(failures_before_success=0, error=RuntimeError("n/a"))
    monkeypatch.setattr(llm_mod, "get_openai_client", lambda: _FakeClient(completions))
    monkeypatch.setattr(settings, "openai_timeout_seconds", 7)

    assert llm_mod.chat([{"role": "user", "content": "hi"}]) == "ok"
    # The SDK default is 600s; every call must carry an explicit bound.
    assert completions.calls[0]["timeout"] == 7.0


def test_chat_retries_transient_errors_then_succeeds(monkeypatch):
    completions = _FakeCompletions(failures_before_success=2, error=RateLimitError("slow down"))
    monkeypatch.setattr(llm_mod, "get_openai_client", lambda: _FakeClient(completions))
    monkeypatch.setattr(llm_mod, "_sleep", lambda _seconds: None)

    assert llm_mod.chat([{"role": "user", "content": "hi"}], max_retries=3) == "ok"
    assert len(completions.calls) == 3


def test_chat_does_not_retry_permanent_errors(monkeypatch):
    completions = _FakeCompletions(failures_before_success=5, error=BadRequestError("bad input"))
    monkeypatch.setattr(llm_mod, "get_openai_client", lambda: _FakeClient(completions))

    with pytest.raises(llm_mod.ResearchLLMError):
        llm_mod.chat([{"role": "user", "content": "hi"}], max_retries=3)
    assert len(completions.calls) == 1


def test_chat_wraps_provider_errors(monkeypatch):
    class Boom(Exception):
        pass

    completions = _FakeCompletions(failures_before_success=99, error=Boom("connection reset"))
    monkeypatch.setattr(llm_mod, "get_openai_client", lambda: _FakeClient(completions))

    with pytest.raises(llm_mod.ResearchLLMError):
        llm_mod.chat([{"role": "user", "content": "hi"}], max_retries=1)


# --------------------------------------------------------------------------
# progress persistence + cancellation reads
# --------------------------------------------------------------------------
class _RecordingRepo:
    def __init__(self, status: str = "retrieving"):
        self.status = status
        self.updates: list[dict] = []
        self.get_any_calls = 0
        self.get_status_calls = 0

    def update(self, research_id, organization_id, fields):
        self.updates.append(dict(fields))
        return dict(fields)

    def get_any(self, research_id):
        self.get_any_calls += 1
        raise AssertionError("get_any pulls the whole row (megabytes); use get_status")

    def get_status(self, research_id):
        self.get_status_calls += 1
        return self.status


def _service_state():
    state = ResearchState(
        research_id="r1", organization_id="org-A", original_query="risks?", config={}
    )
    state.retrieved = [_chunk(index, content="x" * 4000) for index in range(50)]
    state.evidence = []
    return state


def test_progress_write_is_small_and_keeps_the_ui_counters():
    state = _service_state()
    state.status = "retrieving"
    progress = state.to_progress_jsonable()

    assert progress["retrieved_count"] == 50
    assert progress["evidence_count"] == 0
    assert progress["citations_count"] == 0
    assert progress["status"] == "retrieving"
    assert progress["progress"] is True
    # No bulk content: the full payload is written once, at the end.
    assert "retrieved" not in progress
    assert "evidence" not in progress
    assert "final_report" not in progress
    assert len(json.dumps(progress)) < 2000
    assert len(json.dumps(state.to_jsonable())) > 50000


def test_persist_writes_progress_and_cancel_reads_only_status():
    repo = _RecordingRepo(status="cancelled")
    state = _service_state()

    services = graph_mod._build_services(state, "r1", "org-A", repo)
    services.persist(state)

    assert repo.updates[0]["graph_state"]["progress"] is True
    assert repo.updates[0]["status"] == state.status
    assert services.is_cancelled() is True
    assert repo.get_any_calls == 0
    assert repo.get_status_calls == 1


# --------------------------------------------------------------------------
# worker concurrency
# --------------------------------------------------------------------------
def test_research_worker_runs_several_runs_in_parallel(monkeypatch):
    from app.services import job_queue

    jobs = [f"run-{index}" for index in range(4)]
    lock = threading.Lock()
    started = threading.Event()
    release = threading.Event()
    active = 0
    max_active = 0

    def pop_next(timeout=0):
        with lock:
            return jobs.pop(0) if jobs else None

    def run_research(research_id):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        started.set()
        release.wait(10)
        with lock:
            active -= 1

    monkeypatch.setattr(job_queue, "pop_next_research", pop_next)
    monkeypatch.setattr(graph_mod, "run_research", run_research)
    monkeypatch.setattr(settings, "research_worker_concurrency", 3)

    thread = threading.Thread(
        target=graph_mod.run_worker_loop,
        kwargs={"interval": 1, "concurrency": 3},
        daemon=True,
    )
    thread.start()
    try:
        assert started.wait(10), "worker threads never picked up a job"
        deadline = time.time() + 5
        while time.time() < deadline and max_active < 3:
            time.sleep(0.05)
        assert max_active >= 3, f"runs executed sequentially (max concurrency {max_active})"
    finally:
        release.set()
        assert thread.is_alive()


# --------------------------------------------------------------------------
# report sources + background dispatch
# --------------------------------------------------------------------------
class _SourceRepo:
    """Repository double WITH the bulk insert helper."""

    def __init__(self):
        self.bulk_calls: list[list[dict]] = []
        self.single_calls: list[dict] = []

    def create_sources(self, rows):
        self.bulk_calls.append(list(rows))
        return [{"id": f"row-{index}"} for index in range(len(rows))]

    def create_source(self, row):
        self.single_calls.append(row)
        return dict(row)


class _PerRowSourceRepo:
    """Repository double WITHOUT the bulk helper (older callers / doubles)."""

    def __init__(self):
        self.single_calls: list[dict] = []

    def create_source(self, row):
        self.single_calls.append(row)
        return dict(row)


def test_store_sources_inserts_in_bulk_batches(monkeypatch):
    monkeypatch.setattr(settings, "report_source_batch_size", 2)
    repo = _SourceRepo()
    rows = [{"title": f"source-{index}"} for index in range(5)]

    report_service._store_sources(repo, rows)

    assert [len(batch) for batch in repo.bulk_calls] == [2, 2, 1]
    assert repo.single_calls == []
    assert sum(len(batch) for batch in repo.bulk_calls) == len(rows)


def test_store_sources_falls_back_to_per_row_inserts():
    repo = _PerRowSourceRepo()
    rows = [{"title": "a"}, {"title": "b"}]

    report_service._store_sources(repo, rows)

    assert repo.single_calls == rows
    assert report_service._store_sources(repo, []) is None


def test_create_research_dispatches_without_running_inline(monkeypatch):
    from app.services import research_service

    class Repo:
        def create(self, **kwargs):
            return {"id": "run-1", "status": "queued", **kwargs}

    dispatched: list[tuple] = []
    monkeypatch.setattr(research_service, "ResearchRepository", lambda: Repo())
    monkeypatch.setattr(research_service.job_queue, "enqueue_research", lambda _id: False)
    monkeypatch.setattr(
        research_service.background,
        "submit",
        lambda func, *args, **kwargs: dispatched.append((func, args)),
    )

    run = research_service.create_research(
        organization_id="org-A", user_id="user-1", question="What are the risks?"
    )

    assert run["id"] == "run-1"
    assert len(dispatched) == 1
    assert dispatched[0][1] == ("run-1",)
    assert dispatched[0][0] is research_service._run_inline


# --------------------------------------------------------------------------
# end-to-end run through fakes
# --------------------------------------------------------------------------
def test_run_research_completes_and_scores_after_completion(monkeypatch):
    """The happy path: bounded provider calls, small progress writes, the full
    state at the end, and the evaluation dispatched after the run is done."""
    events: list[str] = []
    writes: list[dict] = []

    run = {
        "id": "run-1",
        "organization_id": "org-A",
        "user_id": "user-1",
        "question": "What are the risks in our cloud migration?",
        "status": "queued",
        "config": {},
    }

    class Repo:
        def get_any(self, research_id):
            return dict(run)

        def get_status(self, research_id):
            return run["status"]

        def set_status(self, research_id, organization_id, status, **extra):
            run["status"] = status

        def update(self, research_id, organization_id, fields):
            writes.append(dict(fields))
            run.update(fields)
            return dict(run)

    monkeypatch.setattr(graph_mod, "ResearchRepository", lambda: Repo())
    monkeypatch.setattr(
        graph_mod,
        "_default_retrieve_many",
        lambda org, queries, top_k, filters=None: [
            [_chunk(index) for index in range(3)] for _ in queries
        ],
    )

    def fake_chat(messages, **kwargs):
        system = (messages[0].get("content") or "").lower()
        if "research planner" in system:
            return json.dumps({"sub_questions": ["Security?", "Cost?"]})
        if "important, source-supported" in system or "retrieved document excerpts" in system:
            return json.dumps(
                {
                    "claims": [
                        {"claim": "Migration carries risk.", "source_key": 0, "confidence": 0.9},
                        {"claim": "Costs can rise.", "source_key": 1, "confidence": 0.8},
                    ]
                }
            )
        if "sufficient" in system and "follow_up" in system:
            return json.dumps({"sufficient": True, "gaps": [], "follow_up_queries": []})
        if "grounded research report" in system:
            return "# Executive Summary\n\nMigration risk. [E0]\n# Sources\n\n[E1]\n"
        raise AssertionError(f"unhandled prompt: {system[:50]}")

    monkeypatch.setattr(graph_mod.llm_mod, "chat", fake_chat)
    monkeypatch.setattr(
        graph_mod,
        "_default_llm",
        lambda messages: fake_chat(messages),
    )

    class ReportRepo:
        def __init__(self):
            self.sources: list[dict] = []

        def create(self, **kwargs):
            return {"id": "report-1", **kwargs}

        def create_sources(self, rows):
            self.sources.extend(rows)
            return [{"id": f"src-{index}"} for index in range(len(rows))]

        def create_source(self, row):
            self.sources.append(row)
            return dict(row)

    monkeypatch.setattr(graph_mod.report_service, "ReportRepository", ReportRepo)
    monkeypatch.setattr(
        background,
        "submit",
        lambda func, *args, **kwargs: events.append(f"background:{getattr(func, '__name__', func)}"),
    )
    monkeypatch.setattr(
        graph_mod,
        "background",
        type("BG", (), {"submit": lambda self, func, *a, **k: events.append(f"background:{getattr(func, '__name__', func)}")})(),
    )

    result = graph_mod.run_research("run-1")

    assert result["status"] == "completed"
    assert result["report_id"] == "report-1"
    # Mid-run writes stayed small; the terminal write carries the full state.
    progress_writes = [w for w in writes if (w.get("graph_state") or {}).get("progress")]
    final_writes = [
        w for w in writes if (w.get("graph_state") or {}).get("final_report")
    ]
    assert progress_writes, "the run must report progress as it goes"
    assert final_writes, "the terminal write must persist the full state"
    assert all(len(json.dumps(w["graph_state"])) < 5000 for w in progress_writes)
    # The run is marked completed BEFORE the evaluation is handed off, so
    # scoring never delays the report.
    completed_index = next(
        index for index, field in enumerate(writes) if field.get("status") == "completed"
    )
    assert all(
        field.get("status") != "completed" for field in writes[:completed_index]
    )
    assert events and events[-1].startswith("background:")


def test_run_research_persists_state_when_it_fails(monkeypatch):
    run = {
        "id": "run-2",
        "organization_id": "org-A",
        "user_id": "user-1",
        "question": "boom",
        "status": "queued",
        "config": {},
    }
    writes: list[dict] = []

    class Repo:
        def get_any(self, research_id):
            return dict(run)

        def get_status(self, research_id):
            return run["status"]

        def set_status(self, research_id, organization_id, status, **extra):
            run["status"] = status

        def update(self, research_id, organization_id, fields):
            writes.append(dict(fields))
            run.update(fields)
            return dict(run)

    monkeypatch.setattr(graph_mod, "ResearchRepository", lambda: Repo())

    def llm(messages):
        raise RuntimeError("model exploded")

    services = ResearchServices(llm=llm, retrieve=lambda *a, **k: [], config={})
    monkeypatch.setattr(
        graph_mod, "_build_services", lambda state, run_id, org, repo: services
    )

    result = graph_mod.run_research("run-2")

    assert result["status"] == "failed"
    assert writes[-1]["status"] == "failed"
    # A failed run persists what it gathered (full state), so it stays
    # inspectable instead of only recording an error string.
    assert writes[-1]["graph_state"]["research_id"] == "run-2"
    assert writes[-1]["graph_state"]["status"] == "failed"


# --------------------------------------------------------------------------
# the re-ingestion path still uses the shared helpers
# --------------------------------------------------------------------------
def test_query_embedding_cache_is_used_for_repeated_queries(monkeypatch):
    """Query vectors are a pure function of the text: caching them can never
    return a stale answer, and research re-asks the same question often."""
    calls: list[list[str]] = []
    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, ex=None):
            store[key] = value

    monkeypatch.setattr(embeddings, "get_redis_client", lambda: FakeRedis())
    monkeypatch.setattr(
        embeddings, "embed_texts", lambda texts: calls.append(list(texts)) or [[0.5] for _ in texts]
    )

    first = embeddings.embed_query("What are the risks?")
    second = embeddings.embed_query("What are the risks?")
    other = embeddings.embed_query("Something else")

    assert first == second == [0.5]
    assert len(calls) == 2  # the repeat was served from the cache
    assert other == [0.5]


def test_query_embedding_cache_degrades_without_redis(monkeypatch):
    monkeypatch.setattr(embeddings, "get_redis_client", lambda: None)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        embeddings, "embed_texts", lambda texts: calls.append(list(texts)) or [[0.1] for _ in texts]
    )

    embeddings.embed_query("q")
    embeddings.embed_query("q")
    assert len(calls) == 2  # no cache, no failure


def test_document_service_still_dispatches_processing(monkeypatch):
    """Sanity check that the ingestion side of the shared dispatch is intact."""
    monkeypatch.setattr(document_service.job_queue, "enqueue_document", lambda _id: True)
    assert document_service.start_processing("doc-1") is True


def test_vector_store_search_is_not_double_ensured(monkeypatch):
    """Batch retrieval issues exactly one search per query — no extra
    collection bootstrapping per query."""
    ensured: list[int] = []

    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[0.1] for _ in texts])
    monkeypatch.setattr(
        vector_store, "ensure_collection", lambda client=None: ensured.append(1)
    )
    monkeypatch.setattr(
        vector_store, "_client", lambda: type("C", (), {"query_points": lambda **k: None})()
    )
    monkeypatch.setattr(retrieval.vector_store, "search_vectors", lambda **kwargs: [])

    retrieval.retrieve_context_many("org-A", ["a", "b", "c"])
    assert ensured == []
